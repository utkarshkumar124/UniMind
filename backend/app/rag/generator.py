"""Grounded response generator and modular LLM orchestration for UniMind RAG pipeline."""

import os
import re
import time
import json
import logging
import urllib.request
import urllib.error
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple

from backend.app.core.config import settings
from backend.app.models.schemas import SourceCitation, QueryResponse
from backend.app.rag.retriever import (
    SemanticRetriever,
    RetrievedChunk,
    RetrievalResult,
    retriever as default_retriever,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are UniMind, an official AI academic assistant for university students.
Answer the student's question accurately using ONLY the provided verified document excerpts below.

Guidelines:
1. Cite every factual assertion using bracketed numbers [1], [2], etc., corresponding directly to the provided Excerpt [N].
2. If the provided excerpts do not contain the answer, say: "I do not have sufficient information in the provided university documents to answer this question."
3. Do NOT hallucinate rules, dates, fee amounts, or policies.
4. Keep the tone helpful, professional, and clear.
"""


class LLMProvider(ABC):
    """Abstract interface for grounded response generation."""

    @abstractmethod
    def generate(self, query: str, context_chunks: List[RetrievedChunk]) -> str:
        """Generate a grounded answer for query given retrieved context chunks."""
        pass


class GeminiLLMProvider(LLMProvider):
    """Hosted LLM inference using Google Gemini API."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or settings.get_gemini_api_key() or os.getenv("GEMINI_API_KEY", "")
        self.model = model or getattr(settings, "GEMINI_MODEL", "gemini-1.5-flash")

    def is_available(self) -> bool:
        return bool(self.api_key and self.api_key.strip())

    def generate(self, query: str, context_chunks: List[RetrievedChunk]) -> str:
        if not self.is_available():
            raise RuntimeError("Gemini API key is not configured.")

        # Build prompt
        context_str = "\n\n".join(
            f"--- Excerpt [{i + 1}] (Source: {c.filename or c.doc_id}, Page: {c.page_start}) ---\n{c.text}"
            for i, c in enumerate(context_chunks)
        )

        user_content = f"Verified University Document Excerpts:\n{context_str}\n\nStudent Question: {query}\n\nAnswer:"

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        payload = {
            "contents": [{"parts": [{"text": f"{SYSTEM_PROMPT}\n\n{user_content}"}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 800},
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=12.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "").strip()

        raise RuntimeError("Empty response received from Gemini API.")


class ExtractiveGroundedProvider(LLMProvider):
    """Deterministic, local extractive grounding provider.

    Synthesizes well-structured, scannable Markdown answers directly from retrieved
    excerpts without inventing facts when external LLM APIs are unavailable.
    """

    _STOPWORDS = {
        "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does",
        "for", "from", "how", "i", "if", "in", "is", "it", "lpu", "my", "of",
        "on", "or", "the", "to", "what", "when", "where", "which", "who", "why",
        "with", "you", "your",
    }
    _NOISE_PATTERNS = (
        re.compile(r"^status\s*:\s*", re.I),
        re.compile(r"^q\d+\.\s*", re.I),
        re.compile(r"^title\s*:\s*", re.I),
        re.compile(r"^md\s*[—\-]", re.I),
        re.compile(r"^[a-z_]+/[a-z_]+\.md\b", re.I),
        re.compile(r"\?\s*$"),
        re.compile(r":\s*\d+\.$"),
        re.compile(r"^[\d]+\.$"),
    )

    @classmethod
    def _clean_text_for_splitting(cls, raw: str) -> str:
        """Normalize bullets and protect dots in abbreviations/numbers before sentence split."""
        text = re.sub(r"\s+", " ", raw.replace("\n", " ")).strip().replace("`", "")
        # Strip inline LaTeX wrappers that may survive chunk text
        text = re.sub(r"\\frac\{([^}]*)\}\{([^}]*)\}", r"(\1) / (\2)", text)
        text = text.replace(r"\sum", "Sum").replace(r"\times", "x")
        text = re.sub(r"_\{([^}]*)\}", r" (\1)", text)
        text = text.replace("{", "").replace("}", "")
        # Turn bullet markers into sentence boundaries so list items stay distinct
        text = text.replace("•", ". ")
        # Protect decimals ("3.68") and turn numbered list prefixes into clean boundaries
        text = re.sub(r"(\d)\.(\d)", r"\1<DOT>\2", text)
        text = re.sub(r"(?:(?<=^)|(?<=[\s:]))\d{1,2}\.\s+", ". ", text)
        # Protect multi-dot acronyms like LL.B., B.A., B.B.A., Ph.D., e.g., i.e.
        text = re.sub(r"\b([A-Za-z]{1,2}\.(?:[A-Za-z]{1,2}\.)+)", lambda m: m.group(0).replace(".", "<DOT>"), text)
        # Protect double-dot abbreviations & file extensions
        for dbl, safe in (
            ("e.g.", "for example"),
            ("i.e.", "that is"),
            ("sq.mt.", "sq meters"),
            (".md", "<DOT>md"),
        ):
            text = re.sub(re.escape(dbl), safe, text, flags=re.I)
        for abbr in ("Tech", "Pharm", "Arch", "Plan", "Com", "Hons", "Rs", "Dr", "Mr", "Mrs", "Prof", "vs", "Ext"):
            text = re.sub(rf"\b{re.escape(abbr)}\.", f"{abbr}<DOT>", text, flags=re.I)
        return text

    @classmethod
    def _extract_statements(cls, text: str) -> List[str]:
        """Extract clean, standalone grammatical statements from a chunk."""
        prepared = cls._clean_text_for_splitting(text)
        candidates: List[str] = []
        for seg in prepared.split("."):
            s = seg.replace("<DOT>", ".").strip(" :-–—•")
            s = re.sub(r"^\d{1,2}\)\s*", "", s).strip()
            if len(s) < 38 or len(s.split()) < 7:
                continue
            # Strip noisy leading label prefixes if a full section header got merged
            s = re.sub(
                r"^(?:attendance policy at lpu|campus placements & division of career services|frequently asked questions|general lpu student faqs|direct answer|verification notice|how to calculate tgpa and cgpa|how to apply for a reappear exam \(step-by-step\)|step-by-step formula)\s*[-–—:]\s*",
                "",
                s,
                flags=re.I,
            )
            if any(p.search(s) for p in cls._NOISE_PATTERNS):
                continue
            if s.endswith("?") or re.search(r"\b\d+\)$", s):
                continue
            # Ensure uppercase first character while keeping proper acronyms untouched
            if s and s[0].islower():
                s = s[0].upper() + s[1:]
            if not s.endswith((".", "!")):
                s += "."
            candidates.append(s)
        return candidates

    @classmethod
    def _query_tokens(cls, text: str) -> set:
        words = set(re.findall(r"[a-z0-9]+", text.lower()))
        return {w for w in words if len(w) > 2 and w not in cls._STOPWORDS}

    @classmethod
    def _score_statement(cls, stmt: str, q_tokens: set, chunk_idx: int) -> float:
        s_tokens = cls._query_tokens(stmt)
        overlap = len(q_tokens & s_tokens) if q_tokens else 0
        # Reward concrete figures, dates, portals, and actionable rules
        has_numbers = 1.6 if re.search(r"(\d+%|₹\s?[\d,]+|block-\d+|\b202[5-7]\b|\b\d{4}-\d{6}\b)", stmt, re.I) else 0.0
        has_portal = 0.8 if re.search(r"\b(UMS|LPU Touch|MyClass|LPU Live|LPUAdmit|Pro Bricks|Uni Health Centre)\b", stmt) else 0.0
        is_meta_note = -3.8 if re.search(r"(hosted behind|verification|not verified|not printed|exact rupee fine|partially verified|do not assume one fixed)", stmt, re.I) else 0.0
        rank_bonus = max(0.0, 2.8 - 0.65 * chunk_idx)
        return overlap * 2.2 + has_numbers + has_portal + rank_bonus + is_meta_note

    @classmethod
    def _highlight_key_terms(cls, stmt: str) -> str:
        """Bold key numbers, rupee amounts, and core labels cleanly for readability."""
        # Bold leading "Label: rest" if concise label
        colon_match = re.match(r"^([A-Z][A-Za-z0-9 /&()-]{2,42}):\s+(.+)$", stmt)
        if colon_match:
            label, body = colon_match.groups()
            stmt = f"**{label}:** {body}"
        # Bold percentages and INR currency values if not already bolded
        stmt = re.sub(r"(?<!\*)\b(\d{1,3}(?:\.\d+)?%)(?!\*)", r"**\1**", stmt)
        stmt = re.sub(r"(?<!\*)(₹\s?[\d,]+(?:\s*(?:Lakh|Crore|units?|per semester|/sem))?)(?!\*)", r"**\1**", stmt)
        return stmt

    @classmethod
    def _is_duplicate(cls, stmt: str, chosen: List[str]) -> bool:
        tokens_a = cls._query_tokens(stmt)
        if not tokens_a:
            return False
        for existing in chosen:
            tokens_b = cls._query_tokens(existing)
            if not tokens_b:
                continue
            jaccard = len(tokens_a & tokens_b) / max(1, len(tokens_a | tokens_b))
            if jaccard >= 0.52:
                return True
        return False

    def generate(self, query: str, context_chunks: List[RetrievedChunk]) -> str:
        if not context_chunks:
            return (
                "I do not have sufficient information in the official university documents "
                "to answer this question. Please consult the relevant department or check **UMS**."
            )

        q_tokens = self._query_tokens(query)
        scored_pool: List[Tuple[float, int, str]] = []
        note_candidates: List[Tuple[int, str]] = []

        for idx, chunk in enumerate(context_chunks[:4]):
            cite_num = idx + 1
            for stmt in self._extract_statements(chunk.text):
                if re.search(r"(verify|E-Notice|Academic Ordinance|not verified from an official public)", stmt, re.I) and "minimum" not in stmt.lower():
                    note_candidates.append((cite_num, stmt))
                score = self._score_statement(stmt, q_tokens, idx)
                scored_pool.append((score, cite_num, stmt))

        if not scored_pool:
            fallback_txt = context_chunks[0].text.strip()[:280]
            return f"{fallback_txt} [1]"

        scored_pool.sort(key=lambda item: item[0], reverse=True)

        # Pick the strongest lead sentence for the executive summary
        lead_score, lead_cite, lead_stmt = scored_pool[0]
        chosen_raw = [lead_stmt]
        lead_formatted = f"{self._highlight_key_terms(lead_stmt)} [{lead_cite}]"

        # Gather up to 4 distinct supporting bullet points across all retrieved chunks
        bullets: List[str] = []
        for _, cite_num, stmt in scored_pool[1:]:
            if len(bullets) >= 4:
                break
            if self._is_duplicate(stmt, chosen_raw):
                continue
            chosen_raw.append(stmt)
            bullets.append(f"- {self._highlight_key_terms(stmt)} [{cite_num}]")

        sections: List[str] = [lead_formatted]
        if bullets:
            sections.append("### Key Details\n" + "\n".join(bullets))

        # Add at most one non-duplicate UMS/verification reminder if helpful
        for cite_num, note_stmt in note_candidates:
            if not self._is_duplicate(note_stmt, chosen_raw):
                sections.append(f"> **Note:** {note_stmt} [{cite_num}]")
                break

        return "\n\n".join(sections)


class RAGPipeline:
    """End-to-end Retrieval-Augmented Generation pipeline."""

    def __init__(
        self,
        retriever: Optional[SemanticRetriever] = None,
        llm_provider: Optional[LLMProvider] = None,
    ):
        self.retriever = retriever or default_retriever
        self._custom_llm = llm_provider

    @property
    def llm(self) -> LLMProvider:
        """Select active LLM provider (Gemini if key is configured, else Extractive fallback)."""
        if self._custom_llm:
            return self._custom_llm

        gemini = GeminiLLMProvider()
        if gemini.is_available():
            return gemini

        return ExtractiveGroundedProvider()

    _GREETING_PATTERN = re.compile(
        r"^(?:hi+|hello+|hey+|hlo|namaste|good\s+(?:morning|afternoon|evening)|"
        r"thanks?(?:\s+you)?|bye|goodbye|who\s+are\s+you|what\s+can\s+you\s+do|help)[\s!?.,]*$",
        re.I,
    )

    @classmethod
    def _small_talk_reply(cls, query: str) -> Optional[str]:
        """Return a friendly conversational reply for greetings/thanks without fake citations."""
        cleaned = query.strip()
        if not cls._GREETING_PATTERN.match(cleaned):
            return None
        lower = cleaned.lower()
        if "thank" in lower:
            return "You're welcome! Ask anytime if you have another question about LPU academics, exams, hostels, fees, or campus services."
        if "bye" in lower:
            return "Goodbye! Feel free to come back anytime with questions about LPU policies, deadlines, or student services."
        return (
            "Hi! I'm **UniMind**, your LPU student knowledge assistant.\n\n"
            "### What I Can Help You With\n"
            "- **Attendance & Academics:** 75% eligibility rules, Duty Leave (DL), 2026–27 Academic Calendar, and Open Minors.\n"
            "- **Examinations & CGPA:** CA/MTT/ETE evaluation, TGPA/CGPA formula, reappear dates, scrutiny, and re-evaluation.\n"
            "- **Hostel, Mess & Campus Life:** 2026–27 room & transport fees, allowed appliances, Block-37 Library, and 24x7 Uni Health Centre.\n"
            "- **Fees, Scholarships & Portals:** Programme fees, scholarship brackets, education loans, fee refunds, UMS, and MyClass.\n\n"
            "Ask a specific question below to get grounded answers directly from LPU's knowledge base."
        )

    def answer_query(
        self,
        query: str,
        top_k: int = 4,
        department: Optional[str] = None,
        category: Optional[str] = None,
        min_similarity: Optional[float] = None,
    ) -> QueryResponse:
        """Execute end-to-end RAG workflow from user query to grounded answer."""
        start_time = time.perf_counter()

        greeting_reply = self._small_talk_reply(query)
        if greeting_reply is not None:
            return QueryResponse(
                query=query,
                answer=greeting_reply,
                sources=[],
                total_sources=0,
                latency_ms=(time.perf_counter() - start_time) * 1000.0,
            )

        # 1. Retrieve relevant chunks
        retrieval_res = self.retriever.retrieve(
            query=query,
            top_k=top_k,
            department=department,
            category=category,
            min_similarity=min_similarity,
        )

        # 2. Build verified citations from retrieved chunks
        citations: List[SourceCitation] = []
        for idx, chunk in enumerate(retrieval_res.chunks):
            doc_title = chunk.filename or chunk.metadata.get("filename") or f"Document {chunk.doc_id[:8]}"
            clean_quote = re.sub(r"\s+", " ", chunk.text).replace("`", "").lstrip("•:- ").strip()
            quote_text = clean_quote[:220].strip()
            if len(clean_quote) > 220:
                quote_text += "…"

            citation = SourceCitation(
                n=idx + 1,
                doc_id=chunk.doc_id,
                doc_title=doc_title,
                page=chunk.page_start,
                quote=quote_text,
                score=chunk.score,
            )
            citations.append(citation)

        # 3. Generate answer using selected LLM provider
        try:
            answer_text = self.llm.generate(query, retrieval_res.chunks)
        except Exception as err:
            logger.warning("Primary LLM generation failed (%s); falling back to extractive grounding", err)
            fallback = ExtractiveGroundedProvider()
            answer_text = fallback.generate(query, retrieval_res.chunks)

        total_latency_ms = (time.perf_counter() - start_time) * 1000.0

        return QueryResponse(
            query=query,
            answer=answer_text,
            sources=citations,
            total_sources=len(citations),
            latency_ms=total_latency_ms,
        )


# Default singleton pipeline
rag_pipeline = RAGPipeline()

