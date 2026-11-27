"""Unit tests for GeminiLLMProvider and RAGPipeline LLM fallback behavior."""

import io
import json
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from backend.app.rag.generator import (
    ExtractiveGroundedProvider,
    GeminiLLMProvider,
    LocalOpenAILLMProvider,
    RAGPipeline,
)
from backend.app.rag.retriever import RetrievalResult, RetrievedChunk


def _sample_chunk() -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="doc1#p1#c0",
        doc_id="doc1",
        text="Students must maintain at least 75% attendance in each course to appear in ETE.",
        score=0.91,
        page_start=1,
        page_end=1,
        department="Academic Affairs",
        category="Policy",
        filename="lpu_attendance_policy.pdf",
    )


class TestGeminiLLMProvider(unittest.TestCase):
    """Tests covering Gemini API v1beta request formatting, fallback, and abstention."""

    def test_is_available_respects_key(self):
        self.assertFalse(GeminiLLMProvider(api_key="").is_available())
        self.assertFalse(GeminiLLMProvider(api_key="   ").is_available())
        self.assertTrue(GeminiLLMProvider(api_key="AIzaFakeKey123").is_available())

    def test_empty_context_abstains_without_network_call(self):
        provider = GeminiLLMProvider(api_key="AIzaFakeKey123")
        with patch("urllib.request.urlopen") as mock_open:
            ans = provider.generate("What is the attendance rule?", [])
        mock_open.assert_not_called()
        self.assertIn("do not have sufficient information", ans.lower())

    def test_generate_sends_x_goog_api_key_and_system_instruction(self):
        provider = GeminiLLMProvider(api_key="AIzaSecretTest", model="gemini-2.5-flash")
        fake_resp = MagicMock()
        fake_resp.read.return_value = json.dumps({
            "candidates": [{"content": {"parts": [{"text": "Minimum attendance is **75%** [1]."}]}}]
        }).encode("utf-8")
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = fake_resp
        fake_cm.__exit__.return_value = False

        with patch("urllib.request.urlopen", return_value=fake_cm) as mock_open:
            out = provider.generate("Minimum attendance?", [_sample_chunk()])

        self.assertEqual(out, "Minimum attendance is **75%** [1].")
        req = mock_open.call_args[0][0]
        self.assertIn("models/gemini-2.5-flash:generateContent", req.full_url)
        self.assertNotIn("AIzaSecretTest", req.full_url)
        self.assertEqual(req.headers.get("X-goog-api-key"), "AIzaSecretTest")
        body = json.loads(req.data.decode("utf-8"))
        self.assertIn("systemInstruction", body)
        self.assertIn("lpu_attendance_policy.pdf", body["contents"][0]["parts"][0]["text"])

    def test_model_404_falls_back_to_supported_flash_model(self):
        provider = GeminiLLMProvider(api_key="AIzaSecretTest", model="gemini-1.5-flash")
        http_404 = urllib.error.HTTPError(
            url="https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent",
            code=404,
            msg="Not Found",
            hdrs=None,
            fp=io.BytesIO(b'{"error":{"message":"not found"}}'),
        )
        fake_ok = MagicMock()
        fake_ok.read.return_value = json.dumps({
            "candidates": [{"content": {"parts": [{"text": "Attendance must be 75% [1]."}]}}]
        }).encode("utf-8")
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = fake_ok
        fake_cm.__exit__.return_value = False

        with patch("urllib.request.urlopen", side_effect=[http_404, fake_cm]) as mock_open:
            out = provider.generate("Minimum attendance?", [_sample_chunk()])

        self.assertEqual(out, "Attendance must be 75% [1].")
        self.assertEqual(mock_open.call_count, 2)
        self.assertIn("gemini-3-flash-preview:generateContent", mock_open.call_args_list[1][0][0].full_url)

    def test_model_503_falls_back_to_next_flash_model(self):
        provider = GeminiLLMProvider(api_key="AIzaSecretTest", model="gemini-3-flash-preview")
        http_503 = urllib.error.HTTPError(
            url="https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent",
            code=503,
            msg="Service Unavailable",
            hdrs=None,
            fp=io.BytesIO(b'{"error":{"message":"high demand"}}'),
        )
        fake_ok = MagicMock()
        fake_ok.read.return_value = json.dumps({
            "candidates": [{"content": {"parts": [{"text": "Attendance must be 75% [1]."}]}}]
        }).encode("utf-8")
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = fake_ok
        fake_cm.__exit__.return_value = False

        with patch("urllib.request.urlopen", side_effect=[http_503, fake_cm]) as mock_open:
            out = provider.generate("Minimum attendance?", [_sample_chunk()])

        self.assertEqual(out, "Attendance must be 75% [1].")
        self.assertEqual(mock_open.call_count, 2)
        self.assertIn("gemini-3.8-flash:generateContent", mock_open.call_args_list[1][0][0].full_url)

    def test_rag_pipeline_falls_back_to_extractive_on_gemini_error(self):
        fake_retriever = MagicMock()
        fake_retriever.retrieve.return_value = RetrievalResult(
            query="Minimum attendance?",
            chunks=[_sample_chunk()],
            total_found=1,
            latency_ms=12.0,
        )
        failing_llm = MagicMock()
        failing_llm.generate.side_effect = RuntimeError("401 Unauthorized")

        pipeline = RAGPipeline(retriever=fake_retriever, llm_provider=failing_llm)
        res = pipeline.answer_query("Minimum attendance?")
        self.assertEqual(res.total_sources, 1)
        self.assertEqual(res.provider_used, "extractive-fallback")
        self.assertIn("75%", res.answer)
        self.assertIsInstance(ExtractiveGroundedProvider().generate("Minimum attendance?", [_sample_chunk()]), str)

    def test_local_gemma_provider_calls_openai_compatible_chat_completions(self):
        local = LocalOpenAILLMProvider(base_url="http://localhost:1234/v1", model="google/gemma-4-e4b")
        fake_resp = MagicMock()
        fake_resp.read.return_value = json.dumps({
            "choices": [{"message": {"content": "<thought>check</thought>Attendance is 75% [1]."}}]
        }).encode("utf-8")
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = fake_resp
        fake_cm.__exit__.return_value = False

        with patch("urllib.request.urlopen", return_value=fake_cm) as mock_open:
            out = local.generate("Minimum attendance?", [_sample_chunk()])

        self.assertEqual(out, "Attendance is 75% [1].")
        req = mock_open.call_args[0][0]
        self.assertEqual(req.full_url, "http://localhost:1234/v1/chat/completions")
        body = json.loads(req.data.decode("utf-8"))
        self.assertEqual(body["model"], "google/gemma-4-e4b")
        self.assertEqual(body["reasoning_effort"], "none")

    def test_auto_mode_prefers_local_and_shifts_to_gemini_when_unavailable(self):
        fake_retriever = MagicMock()
        fake_retriever.retrieve.return_value = RetrievalResult(
            query="Minimum attendance?",
            chunks=[_sample_chunk()],
            total_found=1,
            latency_ms=10.0,
        )
        pipeline = RAGPipeline(retriever=fake_retriever)

        # Case 1: Local Gemma 4 available -> picks local first
        with patch.object(LocalOpenAILLMProvider, "is_available", return_value=True), \
             patch.object(LocalOpenAILLMProvider, "generate", return_value="Local 75% [1]."), \
             patch.object(GeminiLLMProvider, "generate") as mock_gemini:
            res_local = pipeline.answer_query("Minimum attendance?", llm_provider="auto")
        self.assertEqual(res_local.answer, "Local 75% [1].")
        self.assertIn("local", res_local.provider_used)
        mock_gemini.assert_not_called()

        # Case 2: Local Gemma 4 unavailable -> shifts automatically to Gemini
        with patch.object(LocalOpenAILLMProvider, "is_available", return_value=False), \
             patch.object(GeminiLLMProvider, "is_available", return_value=True), \
             patch.object(GeminiLLMProvider, "generate", return_value="Gemini 75% [1]."):
            res_shift = pipeline.answer_query("Minimum attendance?", llm_provider="auto")
        self.assertEqual(res_shift.answer, "Gemini 75% [1].")
        self.assertIn("gemini", res_shift.provider_used)

        # Case 3: Local raises runtime error mid-request -> shifts automatically to Gemini
        with patch.object(LocalOpenAILLMProvider, "is_available", return_value=True), \
             patch.object(LocalOpenAILLMProvider, "generate", side_effect=RuntimeError("LM Studio down")), \
             patch.object(GeminiLLMProvider, "is_available", return_value=True), \
             patch.object(GeminiLLMProvider, "generate", return_value="Recovered via Gemini [1]."):
            res_recover = pipeline.answer_query("Minimum attendance?", llm_provider="auto")
        self.assertEqual(res_recover.answer, "Recovered via Gemini [1].")
        self.assertIn("gemini", res_recover.provider_used)

    def test_followup_query_uses_prior_user_turn_for_retrieval(self):
        fake_retriever = MagicMock()
        fake_retriever.retrieve.return_value = RetrievalResult(
            query="expanded",
            chunks=[_sample_chunk()],
            total_found=1,
            latency_ms=8.0,
        )
        pipeline = RAGPipeline(retriever=fake_retriever)
        history = [
            {"role": "user", "content": "What is the minimum attendance requirement at LPU?"},
            {"role": "assistant", "content": "Minimum attendance is 75% [1]."},
        ]
        with patch.object(LocalOpenAILLMProvider, "is_available", return_value=True), \
             patch.object(LocalOpenAILLMProvider, "generate", return_value="Exceptions include Duty Leave [1]."):
            res = pipeline.answer_query("See exceptions and deadlines?", llm_provider="auto", history=history)

        self.assertEqual(res.answer, "Exceptions include Duty Leave [1].")
        called_query = fake_retriever.retrieve.call_args.kwargs["query"]
        self.assertIn("minimum attendance requirement", called_query.lower())
        self.assertIn("exceptions and deadlines", called_query.lower())
        self.assertEqual(len(res.followups), 3)
        self.assertNotIn("What is the minimum attendance requirement at LPU?", res.followups)

    def test_dynamic_followups_match_domain_and_exclude_already_asked(self):
        fake_retriever = MagicMock()
        hostel_chunk = RetrievedChunk(
            chunk_id="h1#p1#c0",
            doc_id="h1",
            text="Hostel rooms range from 4-seater to 1-seater AC/Non-AC. Electric kettles are banned.",
            score=0.89,
            page_start=1,
            page_end=1,
            filename="lpu_hostel_and_mess_handbook_2026_27.pdf",
        )
        fake_retriever.retrieve.return_value = RetrievalResult(
            query="q", chunks=[hostel_chunk], total_found=1, latency_ms=5.0
        )
        pipeline = RAGPipeline(retriever=fake_retriever)
        history = [
            {"role": "user", "content": "What are the 2026-27 hostel fees and allowed appliances?"},
            {"role": "assistant", "content": "Fees depend on AC/Non-AC room occupancy [1]."},
            {"role": "user", "content": "Which electrical appliances are allowed or banned in hostel rooms?"},
            {"role": "assistant", "content": "Electric kettles and heaters are banned [1]."},
        ]
        with patch.object(LocalOpenAILLMProvider, "is_available", return_value=True), \
             patch.object(LocalOpenAILLMProvider, "generate", return_value="Mess plans apply [1]."):
            res = pipeline.answer_query("What about mess rules?", llm_provider="auto", history=history)

        called_query = fake_retriever.retrieve.call_args.kwargs["query"]
        self.assertIn("hostel fees", called_query.lower())
        for fq in res.followups:
            self.assertNotEqual(
                fq.strip().lower(),
                "which electrical appliances are allowed or banned in hostel rooms?",
            )

    def test_transient_url_error_retries_strict_tls_cleanly(self):
        provider = GeminiLLMProvider(api_key="AIzaSecretTest", model="gemini-3-flash-preview")
        url_err = urllib.error.URLError("self-signed certificate in certificate chain")
        fake_ok = MagicMock()
        fake_ok.read.return_value = json.dumps({
            "candidates": [{"content": {"parts": [{"text": "Attendance must be 75% [1]."}]}}]
        }).encode("utf-8")
        fake_cm = MagicMock()
        fake_cm.__enter__.return_value = fake_ok
        fake_cm.__exit__.return_value = False

        with patch("urllib.request.urlopen", side_effect=[url_err, fake_cm]) as mock_open:
            out = provider.generate("Minimum attendance?", [_sample_chunk()])

        self.assertEqual(out, "Attendance must be 75% [1].")
        self.assertEqual(mock_open.call_count, 2)

    def test_followup_containment_excludes_paraphrased_prior_question(self):
        fake_retriever = MagicMock()
        hostel_chunk = RetrievedChunk(
            chunk_id="h1#p1#c0",
            doc_id="h1",
            text="Hostel rooms range from 4-seater to 1-seater AC/Non-AC.",
            score=0.89,
            page_start=1,
            page_end=1,
            filename="lpu_hostel_and_mess_handbook_2026_27.pdf",
        )
        fake_retriever.retrieve.return_value = RetrievalResult(
            query="q", chunks=[hostel_chunk], total_found=1, latency_ms=5.0
        )
        pipeline = RAGPipeline(retriever=fake_retriever)
        history = [
            {"role": "user", "content": "What are the 2026-27 hostel fees and room categories?"},
            {"role": "assistant", "content": "Fees depend on AC/Non-AC occupancy [1]."},
        ]
        with patch.object(LocalOpenAILLMProvider, "is_available", return_value=True), \
             patch.object(LocalOpenAILLMProvider, "generate", return_value="Turnstile gates close at night [1]."):
            res = pipeline.answer_query("What about curfew rules?", llm_provider="auto", history=history)

        for fq in res.followups:
            self.assertNotIn("2026-27 hostel room fees", fq.lower())


if __name__ == "__main__":
    unittest.main()
