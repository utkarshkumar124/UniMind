"""Integration tests for live multilingual-e5-small model encoding and similarity."""

import unittest
import numpy as np
from backend.app.rag.embedder import DenseEmbedder, validate_embedding_matrix


class TestEmbedderIntegration(unittest.TestCase):
    """Integration test suite executing real sentence-transformer inference."""

    @classmethod
    def setUpClass(cls):
        # Load the real multilingual model
        cls.embedder = DenseEmbedder(model_name="intfloat/multilingual-e5-small", use_mock=False)

    def test_live_passage_encoding_contracts(self):
        """Test encoding real English, Hindi, and Hinglish passages with live model."""
        passages = [
            "The final examination schedule will be published on the university student portal.",
            "परीक्षा परिणाम घोषित होने के बाद छात्र पुनर्मूल्यांकन के लिए आवेदन कर सकते हैं।",
            "Hostel admission fee submit karne ki last date 15 December hai.",
        ]

        matrix, stats = self.embedder.embed_passages(passages, batch_size=16)

        # 1. Shape and dtype
        self.assertEqual(matrix.shape, (3, 384))
        self.assertEqual(matrix.dtype, np.float32)

        # 2. Strict validation contract
        validate_embedding_matrix(matrix, expected_dimension=384)

        # 3. Unit norm within strict tolerance
        norms = np.linalg.norm(matrix, axis=1)
        for n in norms:
            self.assertAlmostEqual(float(n), 1.0, places=4)

    def test_live_query_encoding_and_semantic_similarity(self):
        """Test semantic retrieval similarity: query matches relevant passage higher than irrelevant passage."""
        passages = [
            "Students can apply for an official transcript through the registrar office portal.",
            "The university cricket tournament starts next Monday at the sports ground.",
        ]
        doc_matrix = self.embedder.encode_passages(passages)

        query = "How do I get my academic transcript?"
        query_vector = self.embedder.encode_query(query)

        # Cosine similarity is dot product of normalized vectors
        sim_transcript = float(np.dot(doc_matrix[0], query_vector))
        sim_cricket = float(np.dot(doc_matrix[1], query_vector))

        self.assertGreater(sim_transcript, sim_cricket)
        self.assertGreater(sim_transcript, 0.65)


if __name__ == "__main__":
    unittest.main()
