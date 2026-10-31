"""Fast unit tests for dense embedder validation contracts and mock model inference."""

import unittest
import numpy as np
from backend.app.rag.embedder import (
    DenseEmbedder,
    MockEmbeddingModel,
    validate_embedding_matrix,
    VectorValidationError,
)


class TestEmbedderUnit(unittest.TestCase):
    """Unit test suite for vector validation contracts and deterministic mock embedder."""

    def setUp(self):
        self.mock_embedder = DenseEmbedder(use_mock=True)

    def test_valid_embedding_matrix(self):
        """Test that a well-formed 2D float32 normalized matrix passes validation."""
        raw = np.random.randn(5, 384).astype(np.float32)
        norms = np.linalg.norm(raw, axis=1, keepdims=True)
        normalized = raw / norms

        # Should execute without raising
        validate_embedding_matrix(normalized, expected_dimension=384)

    def test_rejection_of_wrong_dimensions(self):
        """Test rejection when vector dimension does not match expected dimension."""
        wrong_dim = np.random.randn(4, 512).astype(np.float32)
        norms = np.linalg.norm(wrong_dim, axis=1, keepdims=True)
        normalized = wrong_dim / norms

        with self.assertRaises(VectorValidationError) as ctx:
            validate_embedding_matrix(normalized, expected_dimension=384)
        self.assertIn("Vector dimension mismatch", str(ctx.exception))

    def test_rejection_of_wrong_dtype(self):
        """Test rejection when array dtype is float64 instead of float32."""
        wrong_dtype = np.random.randn(3, 384).astype(np.float64)
        norms = np.linalg.norm(wrong_dtype, axis=1, keepdims=True)
        normalized = wrong_dtype / norms

        with self.assertRaises(VectorValidationError) as ctx:
            validate_embedding_matrix(normalized, expected_dimension=384)
        self.assertIn("Invalid dtype", str(ctx.exception))

    def test_rejection_of_non_finite_values(self):
        """Test rejection when vector contains NaN or Inf."""
        matrix = np.random.randn(3, 384).astype(np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        normalized = matrix / norms

        # Introduce NaN
        with_nan = normalized.copy()
        with_nan[1, 10] = np.nan
        with self.assertRaises(VectorValidationError) as ctx:
            validate_embedding_matrix(with_nan, expected_dimension=384)
        self.assertIn("non-finite values", str(ctx.exception))

        # Introduce Inf
        with_inf = normalized.copy()
        with_inf[0, 5] = np.inf
        with self.assertRaises(VectorValidationError) as ctx:
            validate_embedding_matrix(with_inf, expected_dimension=384)
        self.assertIn("non-finite values", str(ctx.exception))

    def test_rejection_of_unnormalized_vectors(self):
        """Test rejection when vectors deviate from unit norm ||v|| == 1.0."""
        unnormalized = np.ones((2, 384), dtype=np.float32)
        with self.assertRaises(VectorValidationError) as ctx:
            validate_embedding_matrix(unnormalized, expected_dimension=384)
        self.assertIn("L2 normalization check failed", str(ctx.exception))

    def test_mock_embedder_encodes_passages(self):
        """Test mock embedder outputs valid float32 unit-normalized vectors."""
        passages = [
            "University library hours during exam week.",
            "Fee payment refund policy for undergraduate courses.",
            "Hostel room allocation procedure and timeline.",
        ]
        matrix, stats = self.mock_embedder.embed_passages(passages)

        self.assertEqual(matrix.shape, (3, 384))
        self.assertEqual(matrix.dtype, np.float32)
        self.assertEqual(stats["count"], 3)
        self.assertEqual(stats["dimension"], 384)
        self.assertAlmostEqual(stats["mean_norm"], 1.0, places=4)

    def test_mock_embedder_encodes_query(self):
        """Test query encoding produces a 1D vector of dimension 384 with unit norm."""
        query = "What is the library opening time?"
        vec = self.mock_embedder.encode_query(query)

        self.assertEqual(vec.shape, (384,))
        self.assertEqual(vec.dtype, np.float32)
        self.assertAlmostEqual(float(np.linalg.norm(vec)), 1.0, places=4)

    def test_prefix_assignment(self):
        """Verify E5 model prefix protocols."""
        e5_embedder = DenseEmbedder(model_name="intfloat/multilingual-e5-small", use_mock=True)
        self.assertEqual(e5_embedder.passage_prefix, "passage: ")
        self.assertEqual(e5_embedder.query_prefix, "query: ")

        minilm_embedder = DenseEmbedder(model_name="sentence-transformers/all-MiniLM-L6-v2", use_mock=True)
        self.assertEqual(minilm_embedder.passage_prefix, "")
        self.assertEqual(minilm_embedder.query_prefix, "")


if __name__ == "__main__":
    unittest.main()

