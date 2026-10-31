"""Performance benchmark script for UniMind embedding pipeline and models.
Measures latency (mean, P50, P95), throughput (chunks/sec, tokens/sec), and memory (RSS, heap).
"""

import os
import sys
import time
import tracemalloc
import numpy as np
import psutil

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.app.rag.embedder import DenseEmbedder
from backend.app.rag.chunker import DocumentChunker

SYNTHETIC_PASSAGES = [
    "Academic regulations require full-time undergraduate students to register for at least 15 credits per semester.",
    "Hostel accommodation requests must be submitted through the student affairs portal prior to the semester deadline.",
    "Library facilities are accessible seven days a week, with 24-hour study spaces available during examination periods.",
    "The fee refund policy stipulates an 80% refund if withdrawal occurs within the first two weeks of class instruction.",
    "Students requiring official academic transcripts may place a digital request through the registrar office interface.",
    "Health center services include emergency outpatient consultations and primary medical care for registered students.",
    "Bus shuttle service route A connects the primary academic complex to the student residential blocks every 20 minutes.",
    "Graduation audit checklists must be approved by the academic department advisor prior to the final term commencement.",
]


def run_benchmark(model_name: str = "intfloat/multilingual-e5-small", iterations: int = 50, warmups: int = 10):
    print(f"=== Starting Benchmark for {model_name} ===")
    process = psutil.Process(os.getpid())
    rss_start = process.memory_info().rss / (1024 * 1024)  # MB

    tracemalloc.start()

    embedder = DenseEmbedder(model_name=model_name, use_mock=False)
    chunker = DocumentChunker(tokenizer=embedder.model.tokenizer)

    # Calculate token count across test corpus
    total_tokens = sum(len(embedder.model.tokenizer.encode(p, add_special_tokens=False)) for p in SYNTHETIC_PASSAGES)

    print(f"Loaded model: {model_name}")
    rss_after_load = process.memory_info().rss / (1024 * 1024)
    print(f"Initial Process RSS: {rss_start:.2f} MB -> After Model Load: {rss_after_load:.2f} MB (Delta: {rss_after_load - rss_start:.2f} MB)")

    # 1. Warm-up iterations
    print(f"Executing {warmups} warm-up iterations...")
    for _ in range(warmups):
        _ = embedder.encode_passages(SYNTHETIC_PASSAGES, batch_size=32)

    # 2. Benchmark iterations
    print(f"Executing {iterations} timed benchmark iterations...")
    latencies = []
    t_start = time.perf_counter()
    for _ in range(iterations):
        iter_start = time.perf_counter()
        matrix = embedder.encode_passages(SYNTHETIC_PASSAGES, batch_size=32)
        latencies.append((time.perf_counter() - iter_start) * 1000)  # ms
    t_total = time.perf_counter() - t_start

    # Memory measurement
    current_heap, peak_heap = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    rss_end = process.memory_info().rss / (1024 * 1024)

    # Statistics
    mean_latency = float(np.mean(latencies))
    p50_latency = float(np.percentile(latencies, 50))
    p95_latency = float(np.percentile(latencies, 95))
    total_chunks_processed = iterations * len(SYNTHETIC_PASSAGES)
    total_tokens_processed = iterations * total_tokens
    chunks_per_sec = total_chunks_processed / t_total
    tokens_per_sec = total_tokens_processed / t_total

    print("\n--- Empirical Benchmark Results ---")
    print(f"Model: {model_name}")
    print(f"Passages per batch: {len(SYNTHETIC_PASSAGES)} ({total_tokens} total tokens)")
    print(f"Iterations: {iterations}")
    print(f"Mean Latency: {mean_latency:.2f} ms")
    print(f"P50 Latency:  {p50_latency:.2f} ms")
    print(f"P95 Latency:  {p95_latency:.2f} ms")
    print(f"Throughput:   {chunks_per_sec:.2f} chunks/sec | {tokens_per_sec:.2f} tokens/sec")
    print(f"Python Heap Peak: {peak_heap / (1024 * 1024):.2f} MB")
    print(f"Process RSS Delta: {rss_end - rss_start:.2f} MB (Current RSS: {rss_end:.2f} MB)")
    print("-----------------------------------\n")

    return {
        "model": model_name,
        "mean_latency_ms": round(mean_latency, 2),
        "p50_latency_ms": round(p50_latency, 2),
        "p95_latency_ms": round(p95_latency, 2),
        "chunks_per_sec": round(chunks_per_sec, 2),
        "tokens_per_sec": round(tokens_per_sec, 2),
        "peak_heap_mb": round(peak_heap / (1024 * 1024), 2),
        "rss_delta_mb": round(rss_end - rss_start, 2),
    }


if __name__ == "__main__":
    run_benchmark(iterations=30, warmups=5)
