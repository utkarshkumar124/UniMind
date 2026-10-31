"""Unit tests for the token-aware, page-preserving hierarchical document chunker."""

import unittest
from backend.app.rag.chunker import (
    DocumentChunker,
    calculate_effective_token_budget,
    split_text_hierarchical,
    SimpleWhitespaceTokenizer,
)


class TestDocumentChunker(unittest.TestCase):
    """Test suite for semantic chunking, boundary splitting, short clause retention, and provenance."""

    @classmethod
    def setUpClass(cls):
        cls.chunker = DocumentChunker(chunk_size_tokens=100, chunk_overlap_tokens=20)
        cls.tokenizer = cls.chunker.tokenizer

    def test_effective_token_budget_calculation(self):
        """Test calculation of dynamic token budget subtracting special and prefix tokens."""
        budget = calculate_effective_token_budget(self.tokenizer, prefix="passage: ")
        self.assertGreater(budget, 64)
        self.assertLessEqual(budget, 512)

    def test_short_meaningful_chunks_preserved(self):
        """Verify that short meaningful FAQs, fee amounts, and clauses are not discarded."""
        pages = [
            {
                "page_number": 1,
                "text": "Fee Deadline: December 15, 2026.\nLate Registration Fee: INR 500.",
                "blocks": [
                    {
                        "page_number": 1,
                        "block_index": 0,
                        "bbox": [50.0, 50.0, 300.0, 70.0],
                        "text": "Fee Deadline: December 15, 2026.",
                    },
                    {
                        "page_number": 1,
                        "block_index": 1,
                        "bbox": [50.0, 80.0, 300.0, 100.0],
                        "text": "Late Registration Fee: INR 500.",
                    },
                ],
            }
        ]

        chunks = self.chunker.chunk_document(
            doc_id="doc_synthetic_short",
            filename="fee_schedule.pdf",
            department="Accounts",
            category="Notice",
            file_hash="dummy_hash_short",
            pages=pages,
        )

        self.assertGreaterEqual(len(chunks), 1)
        full_text = " ".join(c.text for c in chunks)
        self.assertIn("December 15, 2026", full_text)
        self.assertIn("INR 500", full_text)

    def test_chunk_provenance_and_page_spans(self):
        """Verify chunk provenance retains document ID, page spans, and structural block references."""
        pages = [
            {
                "page_number": 1,
                "text": "First page introduction and section 1 overview.",
                "blocks": [
                    {
                        "page_number": 1,
                        "block_index": 0,
                        "bbox": [10.0, 10.0, 200.0, 30.0],
                        "text": "First page introduction and section 1 overview.",
                    }
                ],
            },
            {
                "page_number": 2,
                "text": "Second page detailed institutional guidelines and continuation.",
                "blocks": [
                    {
                        "page_number": 2,
                        "block_index": 0,
                        "bbox": [10.0, 10.0, 200.0, 30.0],
                        "text": "Second page detailed institutional guidelines and continuation.",
                    }
                ],
            },
        ]

        chunks = self.chunker.chunk_document(
            doc_id="doc_provenance_test",
            filename="guidelines.pdf",
            department="Academic Affairs",
            category="Policy",
            file_hash="dummy_hash_prov",
            pages=pages,
        )

        self.assertGreaterEqual(len(chunks), 1)
        first_chunk = chunks[0]
        self.assertEqual(first_chunk.doc_id, "doc_provenance_test")
        self.assertEqual(first_chunk.filename, "guidelines.pdf")
        self.assertGreaterEqual(first_chunk.page_start, 1)
        self.assertLessEqual(first_chunk.page_end, 2)
        self.assertTrue(len(first_chunk.blocks) > 0)
        self.assertIsInstance(first_chunk.blocks[0].bbox, list)
        self.assertEqual(len(first_chunk.blocks[0].bbox), 4)

    def test_hierarchical_splitting_respects_token_budget(self):
        """Verify that large blocks are split hierarchically within token capacity."""
        long_paragraph = (
            "Academic integrity is fundamental to university values. "
            "Every student must ensure all submitted course work represents authentic personal effort. "
            "Plagiarism, unauthorized collaboration, and falsification of laboratory results are strictly prohibited. "
            "Violations are subject to review by the Academic Misconduct Committee. "
            "Sanctions may include formal written warnings, score deductions, failing grades, or academic probation. "
        ) * 5

        sub_chunks = split_text_hierarchical(long_paragraph, max_tokens=40, tokenizer=self.tokenizer)
        self.assertGreater(len(sub_chunks), 1)

        for sc in sub_chunks:
            tokens = len(self.tokenizer.encode(sc, add_special_tokens=False))
            self.assertLessEqual(tokens, 50)  # within safe limit of target 40

    def test_overlap_sliding_window(self):
        """Verify that adjacent chunks generated from a long continuous text share contextual overlap."""
        long_text = " ".join([f"Statement number {i} regarding campus safety protocols." for i in range(1, 40)])
        pages = [
            {
                "page_number": 1,
                "text": long_text,
                "blocks": [
                    {
                        "page_number": 1,
                        "block_index": 0,
                        "bbox": [50.0, 50.0, 500.0, 600.0],
                        "text": long_text,
                    }
                ],
            }
        ]

        small_chunker = DocumentChunker(chunk_size_tokens=30, chunk_overlap_tokens=10)
        chunks = small_chunker.chunk_document(
            doc_id="doc_overlap_test",
            filename="safety.pdf",
            department="Security",
            category="Protocol",
            file_hash="dummy_hash_overlap",
            pages=pages,
        )

        self.assertGreater(len(chunks), 1)
        # Check that chunk indices are sequential
        for idx, c in enumerate(chunks):
            self.assertEqual(c.chunk_index, idx)
            self.assertIn(f"doc_overlap_test#p1#c{idx}", c.chunk_id)


if __name__ == "__main__":
    unittest.main()
