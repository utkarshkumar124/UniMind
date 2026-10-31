"""Token-aware, page-preserving hierarchical document chunker."""

import re
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from backend.app.core.config import settings
from backend.app.models.schemas import DocumentChunk, BlockReference

# Fallback basic whitespace tokenizer for lightweight unit test execution without PyTorch
class SimpleWhitespaceTokenizer:
    """Lightweight fallback tokenizer mimicking token length for testing without model downloads."""
    model_max_length: int = 512

    def encode(self, text: str, add_special_tokens: bool = False) -> List[int]:
        # Approximation: ~1 token per 4 characters / words
        words = text.split()
        return list(range(len(words)))

    def build_inputs_with_special_tokens(self, token_ids: List[int]) -> List[int]:
        return [0] + token_ids + [1]


def get_tokenizer_for_model(model_name: Optional[str] = None):
    """Retrieve the exact Hugging Face tokenizer for the active model with caching."""
    name = model_name or settings.EMBEDDING_MODEL_NAME
    try:
        from transformers import AutoTokenizer
        cache_dir = settings.MODEL_CACHE_DIR
        return AutoTokenizer.from_pretrained(name, cache_dir=cache_dir)
    except Exception:
        return SimpleWhitespaceTokenizer()


def calculate_effective_token_budget(tokenizer, prefix: str = "passage: ") -> int:
    """Calculate exact usable text token capacity dynamically using tokenizer metadata."""
    model_max_len = getattr(tokenizer, "max_seq_length", getattr(tokenizer, "model_max_length", 512))
    # Ensure reasonable upper bound if tokenizer reports unbounded sentinel values (e.g. 1e30)
    if not isinstance(model_max_len, int) or model_max_len > 4096:
        model_max_len = 512

    # Measure special tokens added automatically by the tokenizer (e.g. <s> and </s> or [CLS] and [SEP])
    if hasattr(tokenizer, "build_inputs_with_special_tokens"):
        special_tokens_count = len(tokenizer.build_inputs_with_special_tokens([]))
    elif hasattr(tokenizer, "num_special_tokens_to_add"):
        special_tokens_count = tokenizer.num_special_tokens_to_add(pair=False)
    else:
        special_tokens_count = 2

    # Measure exact prefix tokens
    if hasattr(tokenizer, "encode") and prefix:
        prefix_tokens = tokenizer.encode(prefix, add_special_tokens=False)
        prefix_tokens_count = len(prefix_tokens)
    elif prefix:
        prefix_tokens_count = len(prefix.split())
    else:
        prefix_tokens_count = 0

    usable_budget = model_max_len - special_tokens_count - prefix_tokens_count
    return max(usable_budget, 32)


def split_text_hierarchical(text: str, max_tokens: int, tokenizer) -> List[str]:
    """Hierarchically split a text segment into sub-segments respecting sentence and clause boundaries."""
    token_count = len(tokenizer.encode(text, add_special_tokens=False))
    if token_count <= max_tokens:
        return [text]

    # 1. Try splitting by sentence boundaries (. ! ?)
    sentence_delimiters = re.split(r"(?<=[.?!])\s+", text)
    if len(sentence_delimiters) > 1:
        segments = []
        current_segment = []
        current_len = 0
        for s in sentence_delimiters:
            s_len = len(tokenizer.encode(s, add_special_tokens=False))
            if s_len > max_tokens:
                # Recursively split oversized sentence by clause
                sub_parts = split_text_hierarchical(s, max_tokens, tokenizer)
                if current_segment:
                    segments.append(" ".join(current_segment))
                    current_segment = []
                    current_len = 0
                segments.extend(sub_parts)
            elif current_len + s_len <= max_tokens:
                current_segment.append(s)
                current_len += s_len
            else:
                if current_segment:
                    segments.append(" ".join(current_segment))
                current_segment = [s]
                current_len = s_len
        if current_segment:
            segments.append(" ".join(current_segment))
        return segments

    # 2. Try splitting by clauses (; : ,)
    clause_delimiters = re.split(r"(?<=[;:,])\s+", text)
    if len(clause_delimiters) > 1:
        segments = []
        current_segment = []
        current_len = 0
        for c in clause_delimiters:
            c_len = len(tokenizer.encode(c, add_special_tokens=False))
            if current_len + c_len <= max_tokens:
                current_segment.append(c)
                current_len += c_len
            else:
                if current_segment:
                    segments.append(" ".join(current_segment))
                current_segment = [c]
                current_len = c_len
        if current_segment:
            segments.append(" ".join(current_segment))
        return segments

    # 3. Fallback: split by words
    words = text.split()
    segments = []
    curr = []
    for w in words:
        curr.append(w)
        if len(tokenizer.encode(" ".join(curr), add_special_tokens=False)) >= max_tokens:
            segments.append(" ".join(curr))
            curr = []
    if curr:
        segments.append(" ".join(curr))
    return segments or [text]


class DocumentChunker:
    """Decomposes processed documents into token-bounded, page-preserving semantic chunks."""

    def __init__(
        self,
        tokenizer=None,
        target_chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        passage_prefix: str = "passage: ",
        chunk_size_tokens: Optional[int] = None,
        chunk_overlap_tokens: Optional[int] = None,
        model_name: Optional[str] = None,
    ):
        target_name = model_name or settings.EMBEDDING_MODEL_NAME
        self.tokenizer = tokenizer or get_tokenizer_for_model(target_name)
        self.prefix = passage_prefix if "e5" in target_name.lower() else ""
        self.effective_budget = calculate_effective_token_budget(self.tokenizer, self.prefix)

        # Ensure target_chunk_size does not exceed effective model capacity
        desired_size = chunk_size_tokens or target_chunk_size or settings.CHUNK_SIZE_TOKENS
        self.target_chunk_size = min(desired_size, self.effective_budget)

        desired_overlap = chunk_overlap_tokens or chunk_overlap or settings.CHUNK_OVERLAP_TOKENS
        self.chunk_overlap = min(desired_overlap, int(self.target_chunk_size * 0.3))

    def chunk_document(
        self,
        doc_data: Optional[Dict[str, Any]] = None,
        *,
        doc_id: Optional[str] = None,
        filename: Optional[str] = None,
        department: Optional[str] = None,
        category: Optional[str] = None,
        file_hash: Optional[str] = None,
        pages: Optional[List[Dict[str, Any]]] = None,
    ) -> List[DocumentChunk]:
        """Chunk a processed document while preserving exact page and structural block provenance.

        Accepts either an ingestion dictionary or individual keyword arguments.
        """
        if doc_data is not None:
            doc_id = doc_data.get("doc_id", doc_id or "unknown")
            filename = doc_data.get("filename", filename or "unnamed.pdf")
            department = doc_data.get("department", department or "General")
            category = doc_data.get("category", category or "Policy")
            file_hash = doc_data.get("file_hash", file_hash or "")
            pages = doc_data.get("pages", pages or [])
        else:
            doc_id = doc_id or "unknown"
            filename = filename or "unnamed.pdf"
            department = department or "General"
            category = category or "Policy"
            file_hash = file_hash or ""
            pages = pages or []
        now_iso = datetime.now(timezone.utc).isoformat()

        chunks: List[DocumentChunk] = []
        chunk_index = 0

        for page in pages:
            # Skip empty pages
            if page.get("is_empty"):
                continue

            page_num = page.get("page_number", 1)
            blocks = page.get("blocks", [])

            if not blocks:
                page_text = (page.get("text") or "").strip()
                if not page_text or not re.search(r"[a-zA-Z0-9]", page_text):
                    continue
                # Synthesize block representation from raw page text
                blocks = [{
                    "block_number": 0,
                    "bbox": [0.0, 0.0, 0.0, 0.0],
                    "text": page_text,
                }]

            current_chunk_texts: List[str] = []
            current_chunk_blocks: List[BlockReference] = []
            current_tokens = 0

            for blk in blocks:
                raw_blk_text = (blk.get("text") or "").strip()
                # Exclude purely non-alphanumeric noise blocks
                if not raw_blk_text or not re.search(r"[a-zA-Z0-9]", raw_blk_text):
                    continue

                blk_ref = BlockReference(
                    page_number=page_num,
                    block_index=blk.get("block_number", 0),
                    bbox=blk.get("bbox", [0.0, 0.0, 0.0, 0.0]),
                )

                blk_tokens = len(self.tokenizer.encode(raw_blk_text, add_special_tokens=False))

                # If this single block exceeds target chunk size, split it hierarchically
                if blk_tokens > self.target_chunk_size:
                    # Flush current accumulator first if non-empty
                    if current_chunk_texts:
                        combined_text = "\n\n".join(current_chunk_texts).strip()
                        c_toks = len(self.tokenizer.encode(combined_text, add_special_tokens=False))
                        chunks.append(DocumentChunk(
                            chunk_id=f"{doc_id}#p{page_num}#c{chunk_index}",
                            doc_id=doc_id,
                            filename=filename,
                            department=department,
                            category=category,
                            page_start=page_num,
                            page_end=page_num,
                            chunk_index=chunk_index,
                            blocks=list(current_chunk_blocks),
                            text=combined_text,
                            token_count=c_toks,
                            char_count=len(combined_text),
                            file_hash_sha256=file_hash,
                            embedding_offset=chunk_index,
                            created_at=now_iso,
                        ))
                        chunk_index += 1
                        current_chunk_texts = []
                        current_chunk_blocks = []
                        current_tokens = 0

                    # Sub-split oversized block
                    sub_segments = split_text_hierarchical(raw_blk_text, self.target_chunk_size, self.tokenizer)
                    for sub in sub_segments:
                        sub = sub.strip()
                        if not sub or not re.search(r"[a-zA-Z0-9]", sub):
                            continue
                        sub_toks = len(self.tokenizer.encode(sub, add_special_tokens=False))
                        chunks.append(DocumentChunk(
                            chunk_id=f"{doc_id}#p{page_num}#c{chunk_index}",
                            doc_id=doc_id,
                            filename=filename,
                            department=department,
                            category=category,
                            page_start=page_num,
                            page_end=page_num,
                            chunk_index=chunk_index,
                            blocks=[blk_ref],
                            text=sub,
                            token_count=sub_toks,
                            char_count=len(sub),
                            file_hash_sha256=file_hash,
                            embedding_offset=chunk_index,
                            created_at=now_iso,
                        ))
                        chunk_index += 1
                    continue

                # Normal accumulation
                if current_tokens + blk_tokens <= self.target_chunk_size:
                    current_chunk_texts.append(raw_blk_text)
                    current_chunk_blocks.append(blk_ref)
                    current_tokens += blk_tokens
                else:
                    # Emit current chunk
                    if current_chunk_texts:
                        combined_text = "\n\n".join(current_chunk_texts).strip()
                        c_toks = len(self.tokenizer.encode(combined_text, add_special_tokens=False))
                        chunks.append(DocumentChunk(
                            chunk_id=f"{doc_id}#p{page_num}#c{chunk_index}",
                            doc_id=doc_id,
                            filename=filename,
                            department=department,
                            category=category,
                            page_start=page_num,
                            page_end=page_num,
                            chunk_index=chunk_index,
                            blocks=list(current_chunk_blocks),
                            text=combined_text,
                            token_count=c_toks,
                            char_count=len(combined_text),
                            file_hash_sha256=file_hash,
                            embedding_offset=chunk_index,
                            created_at=now_iso,
                        ))
                        chunk_index += 1

                    # Reset with overlap if applicable
                    current_chunk_texts = [raw_blk_text]
                    current_chunk_blocks = [blk_ref]
                    current_tokens = blk_tokens

            # Flush residual page chunk
            if current_chunk_texts:
                combined_text = "\n\n".join(current_chunk_texts).strip()
                # Short chunks (fees, room numbers, dates) are explicitly preserved!
                if re.search(r"[a-zA-Z0-9]", combined_text):
                    c_toks = len(self.tokenizer.encode(combined_text, add_special_tokens=False))
                    chunks.append(DocumentChunk(
                        chunk_id=f"{doc_id}#p{page_num}#c{chunk_index}",
                        doc_id=doc_id,
                        filename=filename,
                        department=department,
                        category=category,
                        page_start=page_num,
                        page_end=page_num,
                        chunk_index=chunk_index,
                        blocks=list(current_chunk_blocks),
                        text=combined_text,
                        token_count=c_toks,
                        char_count=len(combined_text),
                        file_hash_sha256=file_hash,
                        embedding_offset=chunk_index,
                        created_at=now_iso,
                    ))
                    chunk_index += 1

        return chunks

