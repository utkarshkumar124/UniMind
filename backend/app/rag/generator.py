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

SYSTEM_PROMPT = """You are UniMind, an official AI academic assistant for Lovely Professional University (LPU) students.
Answer the student's question thoroughly and accurately using ONLY the provided verified document excerpts below.

Guidelines:
1. Extract ALL concrete dates, deadlines, percentages, fee amounts, rules, steps, and exceptions present in the excerpts. Use clean Markdown headings and bullet points so the answer is scannable.
2. When Conversation History is given, stay strictly on that established topic (for example, if the user previously asked about hostels or fees, answer the follow-up specifically about hostels or fees) rather than drifting to unrelated topics.
3. NEVER write a vague one-sentence brush-off (like "check the portal for deadlines") when specific dates, figures, or procedures are already written in the excerpts.
4. Cite every factual assertion using bracketed numbers [1], [2], etc., matching Excerpt [N].
5. If none of the provided excerpts contain the answer, say: "I do not have sufficient information in the provided university documents to answer this question."
6. Do NOT hallucinate rules, dates, fee amounts, or policies not supported by the excerpts.
"""


class LLMProvider(ABC):
    """Abstract interface for grounded response generation."""

    @abstractmethod
    def generate(self, query: str, context_chunks: List[RetrievedChunk]) -> str:
        """Generate a grounded answer for query given retrieved context chunks."""
        pass


class GeminiLLMProvider(LLMProvider):
    """Hosted LLM inference using Google Gemini API (v1beta generateContent)."""

    _FALLBACK_MODELS = (
        "gemini-3-flash-preview",
        "gemini-3.8-flash",
        "gemini-3.6-flash",
        "gemini-3.5-flash",
    )

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_output_tokens: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
    ):
        if api_key is not None:
            self.api_key = api_key.strip()
        else:
            self.api_key = (
                settings.get_gemini_api_key()
                or os.getenv("GEMINI_API_KEY", "")
            ).strip()
        self.model = (model or getattr(settings, "GEMINI_MODEL", "gemini-3-flash-preview")).strip()
        self.temperature = (
            temperature if temperature is not None else getattr(settings, "GEMINI_TEMPERATURE", 0.2)
        )
        self.max_output_tokens = (
            max_output_tokens
            if max_output_tokens is not None
            else getattr(settings, "GEMINI_MAX_OUTPUT_TOKENS", 1024)
        )
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else getattr(settings, "GEMINI_TIMEOUT_SECONDS", 20.0)
        )

    def is_available(self) -> bool:
        return bool(self.api_key)

    def _candidate_models(self) -> List[str]:
        candidates = [self.model] + list(self._FALLBACK_MODELS)
        seen = []
        for m in candidates:
            if m and m not in seen:
                seen.append(m)
        return seen

    def _invoke_model(self, model_name: str, payload_bytes: bytes) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        req = urllib.request.Request(
            url,
            data=payload_bytes,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        candidates = data.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            text_parts = [p.get("text", "") for p in parts if p.get("text")]
            combined = "\n".join(text_parts).strip()
            if combined:
                return combined
        raise RuntimeError(f"Empty response received from Gemini model '{model_name}'.")

    def generate(self, query: str, context_chunks: List[RetrievedChunk]) -> str:
        if not self.is_available():
            raise RuntimeError("Gemini API key is not configured.")

        if not context_chunks:
            return (
                "I do not have sufficient information in the provided university documents "
                "to answer this question. Please verify on **UMS** or consult the relevant department."
            )

        context_str = "\n\n".join(
            f"--- Excerpt [{i + 1}] (Source: {c.filename or c.doc_id}, Page: {c.page_start}, Score: {c.score:.3f}) ---\n{c.text}"
            for i, c in enumerate(context_chunks)
        )

        user_content = (
            f"Verified University Document Excerpts:\n{context_str}\n\n"
            f"Student Question: {query}\n\n"
            "Format a clear, accurate Markdown response citing [1], [2], etc. for every factual claim:"
        )

        payload: Dict[str, Any] = {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": user_content}]}],
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": self.max_output_tokens,
                "thinkingConfig": {"thinkingBudget": 0},
            },
        }
        payload_bytes = json.dumps(payload).encode("utf-8")

        last_err: Optional[Exception] = None
        for model_name in self._candidate_models():
            for attempt in range(2):
                try:
                    return self._invoke_model(model_name, payload_bytes)
                except urllib.error.HTTPError as http_err:
                    body = ""
                    try:
                        body = http_err.read().decode("utf-8", errors="ignore")[:240]
                    except Exception:
                        pass
                    if http_err.code == 400 and "thinkingConfig" in payload.get("generationConfig", {}):
                        payload_no_think = json.loads(payload_bytes.decode("utf-8"))
                        payload_no_think.get("generationConfig", {}).pop("thinkingConfig", None)
                        try:
                            return self._invoke_model(model_name, json.dumps(payload_no_think).encode("utf-8"))
                        except Exception as retry_err:
                            last_err = retry_err
                            break
                    last_err = RuntimeError(f"Gemini HTTP {http_err.code} on {model_name}: {body or http_err.reason}")
                    if http_err.code in (404, 429, 503):
                        logger.warning("Gemini model '%s' returned HTTP %d; trying next candidate.", model_name, http_err.code)
                        break
                    raise last_err from http_err
                except urllib.error.URLError as url_err:
                    last_err = url_err
                    logger.warning(
                        "Gemini transport/TLS error on '%s' (attempt %d/2): %s",
                        model_name,
                        attempt + 1,
                        url_err,
                    )
                    if attempt == 0:
                        continue
                    break
                except TimeoutError as timeout_err:
                    last_err = timeout_err
                    logger.warning("Gemini model '%s' timed out; trying next candidate.", model_name)
                    break
        if last_err is not None:
            raise last_err
        raise RuntimeError("No Gemini models configured.")


class LocalOpenAILLMProvider(LLMProvider):
    """Local LLM inference via OpenAI-compatible REST endpoint (LM Studio Gemma 4 / Ollama)."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
        reasoning_effort: Optional[str] = None,
    ):
        raw_url = base_url if base_url is not None else getattr(settings, "LOCAL_LLM_BASE_URL", "http://localhost:1234/v1")
        self.base_url = raw_url.strip().rstrip("/")
        self.model = (
            model if model is not None else getattr(settings, "LOCAL_LLM_MODEL", "google/gemma-4-e4b")
        ).strip()
        self.temperature = (
            temperature if temperature is not None else getattr(settings, "GEMINI_TEMPERATURE", 0.2)
        )
        self.max_tokens = (
            max_tokens if max_tokens is not None else getattr(settings, "LOCAL_LLM_MAX_TOKENS", 384)
        )
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else getattr(settings, "LOCAL_LLM_TIMEOUT_SECONDS", 15.0)
        )
        self.reasoning_effort = (
            reasoning_effort
            if reasoning_effort is not None
            else getattr(settings, "LOCAL_LLM_REASONING_EFFORT", "none")
        ).strip()

    def is_available(self) -> bool:
        """Probe local OpenAI-compatible server /models endpoint quickly."""
        if not self.base_url:
            return False
        try:
            req = urllib.request.Request(f"{self.base_url}/models", method="GET")
            with urllib.request.urlopen(req, timeout=0.8) as resp:
                if resp.status != 200:
                    return False
                data = json.loads(resp.read().decode("utf-8"))
                models = [str(m.get("id", "")) for m in data.get("data", []) if m.get("id")]
                if models and self.model not in models:
                    # Use first loaded model if configured ID differs slightly
                    self.model = models[0]
                return bool(models)
        except Exception:
            return False

    @staticmethod
    def _clean_output(text: str) -> str:
        """Strip optional inline <thought> blocks while preserving clean Markdown citations."""
        cleaned = re.sub(r"<thought>.*?</thought>", "", text, flags=re.S | re.I).strip()
        return cleaned

    def generate(self, query: str, context_chunks: List[RetrievedChunk]) -> str:
        if not self.base_url:
            raise RuntimeError("Local LLM base URL is not configured.")

        if not context_chunks:
            return (
                "I do not have sufficient information in the provided university documents "
                "to answer this question. Please verify on **UMS** or consult the relevant department."
            )

        # Pass all top retrieved excerpts cleanly bounded for fast local prefill
        trimmed_chunks = context_chunks[:4]
        context_str = "\n\n".join(
            f"--- Excerpt [{i + 1}] (Source: {c.filename or c.doc_id}, Page: {c.page_start}) ---\n{c.text[:1300]}"
            for i, c in enumerate(trimmed_chunks)
        )

        user_content = (
            f"Verified University Document Excerpts:\n{context_str}\n\n"
            f"Student Question: {query}\n\n"
            "Write a structured Markdown answer listing every relevant date, exception, fee, or rule from the excerpts with [1], [2] citations:"
        )

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort

        def _post(body_dict: Dict[str, Any]) -> Dict[str, Any]:
            req = urllib.request.Request(
                f"{self.base_url}/chat/completions",
                data=json.dumps(body_dict).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                return json.loads(resp.read().decode("utf-8"))

        try:
            data = _post(payload)
        except urllib.error.HTTPError as http_err:
            if http_err.code == 400 and "reasoning_effort" in payload:
                payload.pop("reasoning_effort", None)
                data = _post(payload)
            else:
                raise

        choices = data.get("choices", [])
        if choices:
            msg = choices[0].get("message", {})
            raw_content = str(msg.get("content") or "").strip()
            cleaned = self._clean_output(raw_content)
            if cleaned:
                return cleaned
        raise RuntimeError(f"Empty response received from local LLM '{self.model}'.")


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
        """Select active LLM provider according to configured priority."""
        provider, _ = self._select_provider()
        return provider

    def _select_provider(self, preferred_mode: Optional[str] = None) -> Tuple[LLMProvider, str]:
        """Return (provider_instance, label) according to requested mode."""
        if self._custom_llm:
            return self._custom_llm, type(self._custom_llm).__name__

        mode = (preferred_mode or getattr(settings, "LLM_PROVIDER", "auto") or "auto").strip().lower()
        gemini = GeminiLLMProvider()
        local_llm = LocalOpenAILLMProvider()

        if mode == "extractive":
            return ExtractiveGroundedProvider(), "extractive-fallback"

        if mode == "gemini":
            if gemini.is_available():
                return gemini, f"gemini ({gemini.model})"
            return ExtractiveGroundedProvider(), "extractive-fallback"

        # Default "auto" (and "local" when unavailable): Local Gemma 4 -> Cloud Gemini -> Extractive Grounding
        if local_llm.is_available():
            return local_llm, f"local ({local_llm.model})"
        if gemini.is_available():
            return gemini, f"gemini ({gemini.model})"
        return ExtractiveGroundedProvider(), "extractive-fallback"

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

    _FOLLOWUP_BANK: Dict[str, List[str]] = {
        "lpu_attendance_policy.pdf": [
            "How is Duty Leave (DL) applied and counted toward 75%?",
            "What happens if my attendance falls short before ETE?",
            "Is there a medical relaxation buffer below 80% aggregate?",
            "How can I report a wrong attendance mark on UMS/RMS?",
        ],
        "lpu_examinations_and_grading.pdf": [
            "How are TGPA and CGPA calculated on the 10-point scale?",
            "When are the 2026-27 reappear exams and application deadlines?",
            "What is the process for ETE answer booklet scrutiny & re-evaluation?",
            "How do CA, MTT, and ETE components combine in grading?",
        ],
        "lpu_fees_scholarships_and_refunds_2026_27.pdf": [
            "What scholarship brackets (1 to 4) reduce tuition fees?",
            "What is the LPU fee refund policy before session start?",
            "How do semester exam fees and education loans work?",
            "What happens to fees if paid after the payment deadline?",
        ],
        "lpu_hostel_and_mess_handbook_2026_27.pdf": [
            "Which electrical appliances are allowed or banned in hostel rooms?",
            "What are the 2026-27 hostel room fees and AC/Non-AC options?",
            "What mess, laundry, and residential rules apply to hostelers?",
            "How do hostel leave passes and reporting rules work?",
        ],
        "lpu_placements_and_career_services.pdf": [
            "Which top recruiters hire at LPU and what are recent package stats?",
            "What Career Enhancement (CPE) training platforms does LPU offer?",
            "How does the Division of Career Services support internships?",
        ],
        "lpu_campus_services_medical_library_transport.pdf": [
            "Where is the Central Library and what are its facilities?",
            "What 24x7 medical and ambulance services are at Uni Health Centre?",
            "What campus bus routes and student transport pass options exist?",
        ],
        "lpu_student_portals_and_digital_services.pdf": [
            "What tasks are handled in UMS vs LPU Touch vs MyClass?",
            "How do students raise tickets on RMS and LPU Live?",
            "How do I access remote digital library journals off-campus?",
        ],
        "lpu_policies_discipline_anti_ragging_grievance.pdf": [
            "How do I file a Level 1–3 grievance or anti-ragging report?",
            "What disciplinary actions apply for campus misconduct or ragging?",
            "How do I apply for a Bonafide certificate or Migration via UMS?",
        ],
        "lpu_academics_and_calendar_2026_27.pdf": [
            "What are the key 2026-27 Autumn & Spring Term calendar dates?",
            "How do Open Minors, electives, and CBCS credits work?",
            "What are the course add/drop and academic progression rules?",
        ],
        "lpu_comprehensive_student_faqs.pdf": [
            "How is minimum 75% attendance checked for ETE eligibility?",
            "How do I apply for reappear exams or grade scrutiny?",
            "What are the 2026-27 fee refund and scholarship timelines?",
        ],
        "lpu_university_overview_and_contacts.pdf": [
            "Who are the key LPU helplines, Registrar, and student contacts?",
            "Which accreditations (NAAC, NBA, UGC) does LPU hold?",
            "What accessibility and banking facilities exist on campus?",
        ],
    }

    _GENERIC_STARTER_FOLLOWUPS: List[str] = [
        "What is the 2026 B.Tech CSE semester tuition and exam fee?",
        "What is the minimum attendance rule and Duty Leave process?",
        "How are TGPA, CGPA, and reappear exams structured?",
        "What are the 2026-27 hostel fees and allowed appliances?",
        "How do I file a grievance or apply for a Bonafide certificate?",
        "Where is the Central Library and 24x7 Uni Health Centre?",
    ]

    @classmethod
    def _is_generic_followup(cls, text: str) -> bool:
        cleaned = text.strip().lower()
        words = cleaned.split()
        if len(words) <= 4:
            return True
        if re.search(r"\b(it|its|this|that|they|them|their|those|these)\b", cleaned):
            return True
        return bool(
            re.match(
                r"^(?:see|check|what about|how about|and |also |explain|compare|more|details|exceptions|deadlines|what steps|tell me more)\b",
                cleaned,
            )
        )

    @classmethod
    def _resolve_followup_query(
        cls,
        query: str,
        history: Optional[List[Dict[str, str]]],
    ) -> Tuple[str, str]:
        """Expand short/ambiguous follow-ups using root topic + recent Q&A turn."""
        if not history:
            return query, query

        norm_current = query.strip().lower()
        prior_users: List[str] = []
        last_assistant = ""
        for m in history:
            role = str(m.get("role", "")).lower()
            content = str(m.get("content", "")).strip()
            if not content:
                continue
            if role == "user" and content.lower() != norm_current:
                prior_users.append(content)
            elif role == "assistant":
                last_assistant = content

        if not prior_users:
            return query, query

        if not cls._is_generic_followup(query):
            return query, query

        substantive = [u for u in prior_users if not cls._is_generic_followup(u)]
        anchor_topic = substantive[0] if substantive else prior_users[0]
        latest_user = prior_users[-1]

        if anchor_topic.lower() != latest_user.lower():
            retrieval_q = f"{anchor_topic} — {latest_user} — {query}"
        else:
            retrieval_q = f"{anchor_topic} — {query}"

        history_lines = [f"Topic/Earlier Question: {anchor_topic}"]
        if latest_user.lower() != anchor_topic.lower():
            history_lines.append(f"Previous Question: {latest_user}")
        if last_assistant:
            snippet = re.sub(r"\s+", " ", last_assistant).strip()[:450]
            history_lines.append(f"Previous Assistant Answer: {snippet}")
        llm_q = (
            "Conversation History:\n"
            + "\n".join(history_lines)
            + f"\n\nCurrent Follow-up Question: {query}"
        )
        return retrieval_q, llm_q

    @classmethod
    def _build_followups(
        cls,
        query: str,
        chunks: List[RetrievedChunk],
        history: Optional[List[Dict[str, str]]],
    ) -> List[str]:
        """Generate 3 fresh, topic-matched follow-ups excluding already asked questions."""
        asked_norm = {query.strip().lower().rstrip("?.,!")}
        if history:
            for m in history:
                if str(m.get("role", "")).lower() == "user":
                    txt = str(m.get("content", "")).strip().lower().rstrip("?.,!")
                    if txt:
                        asked_norm.add(txt)

        def _is_already_asked(cand: str) -> bool:
            c_norm = cand.strip().lower().rstrip("?.,!")
            if c_norm in asked_norm:
                return True
            c_tokens = ExtractiveGroundedProvider._query_tokens(c_norm)
            for prev in asked_norm:
                p_tokens = ExtractiveGroundedProvider._query_tokens(prev)
                if c_tokens and p_tokens:
                    inter = len(c_tokens & p_tokens)
                    jaccard = inter / max(1, len(c_tokens | p_tokens))
                    contain = inter / max(1, min(len(c_tokens), len(p_tokens)))
                    if jaccard >= 0.72 or contain >= 0.65:
                        return True
            return False

        candidates: List[str] = []
        seen_docs: List[str] = []
        for ch in chunks:
            fname = ch.filename or ch.metadata.get("filename") or ""
            if fname and fname not in seen_docs:
                seen_docs.append(fname)
                for q_opt in cls._FOLLOWUP_BANK.get(fname, []):
                    if q_opt not in candidates:
                        candidates.append(q_opt)

        for fallback_q in cls._GENERIC_STARTER_FOLLOWUPS:
            if fallback_q not in candidates:
                candidates.append(fallback_q)

        fresh: List[str] = []
        for c in candidates:
            if not _is_already_asked(c):
                fresh.append(c)
            if len(fresh) >= 3:
                break
        return fresh

    def answer_query(
        self,
        query: str,
        top_k: int = 4,
        department: Optional[str] = None,
        category: Optional[str] = None,
        min_similarity: Optional[float] = None,
        llm_provider: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
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
                provider_used="small-talk",
                followups=self._GENERIC_STARTER_FOLLOWUPS[:3],
            )

        retrieval_query, llm_query = self._resolve_followup_query(query, history)

        # 1. Retrieve relevant chunks
        retrieval_res = self.retriever.retrieve(
            query=retrieval_query,
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

        # 3. Generate answer using selected LLM provider with automatic fallback chain
        mode = (llm_provider or getattr(settings, "LLM_PROVIDER", "auto") or "auto").strip().lower()
        provider, provider_label = self._select_provider(mode)
        try:
            answer_text = provider.generate(llm_query, retrieval_res.chunks)
        except Exception as err:
            logger.warning("Primary LLM generation (%s) failed (%s)", provider_label, err)
            answer_text = ""
            # Automatically shift from Local Gemma 4 -> Cloud Gemini before Extractive fallback
            if mode in ("auto", "local") and not self._custom_llm and isinstance(provider, LocalOpenAILLMProvider):
                gemini = GeminiLLMProvider()
                if gemini.is_available():
                    try:
                        answer_text = gemini.generate(llm_query, retrieval_res.chunks)
                        provider_label = f"gemini ({gemini.model})"
                    except Exception as gem_err:
                        logger.warning("Cloud Gemini fallback failed (%s)", gem_err)
            if not answer_text:
                fallback = ExtractiveGroundedProvider()
                answer_text = fallback.generate(retrieval_query, retrieval_res.chunks)
                provider_label = "extractive-fallback"

        total_latency_ms = (time.perf_counter() - start_time) * 1000.0
        followups = self._build_followups(query, retrieval_res.chunks, history)

        return QueryResponse(
            query=query,
            answer=answer_text,
            sources=citations,
            total_sources=len(citations),
            latency_ms=total_latency_ms,
            provider_used=provider_label,
            followups=followups,
        )


# Default singleton pipeline
rag_pipeline = RAGPipeline()

