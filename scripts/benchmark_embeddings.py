"""Performance benchmark script for UniMind embedding pipeline and models.
Measures latency (mean, P50, P95), throughput (chunks/sec, tokens/sec), and memory (RSS, heap).
Evaluates 32 synthetic chunks of ~150 tokens across 10 warmup and 50 timed iterations.
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

# 32 substantive synthetic university policy paragraphs (~130-160 words / ~150 tokens each)
SYNTHETIC_32_CHUNKS = [
    "Academic regulations govern undergraduate course registration, semester credit limits, and degree progression milestones across all accredited university faculties. Full-time students must maintain enrollment in at least fifteen credits per semester, up to a maximum ceiling of twenty-four credits with cumulative grade point average approval. Any student failing to satisfy minimum semester credit hours will be placed on probationary academic standing by the registrar office.",
    "The institutional grading structure is based on a ten-point relative grading scale where academic performance is evaluated through continuous internal assessments and comprehensive term examinations. Grade points earned correspond directly to percentage cutoffs established by departmental boards of study, with letter grades ranging from Outstanding to Fail. Cumulative Grade Point Averages are recalculated at the end of each academic semester following final grade moderation.",
    "Hostel accommodation and campus residential life require strict compliance with dormitory quiet hours, visitor authorization protocols, and room inventory sign-off procedures. Residents must register biometric check-ins prior to the designated ten o'clock evening curfew unless an authorized late entry slip has been approved by the hostel warden. Subletting dormitory rooms or hosting unauthorized overnight visitors constitutes an immediate violation of residential codes.",
    "Tuition fee refund requests must be formally submitted through the university finance portal and will be processed in accordance with established statutory guidelines. If a student formally requests withdrawal from a degree program prior to commencement of orientation, a full refund less administrative processing fees is disbursed. Withdrawals occurring after two weeks of instructional sessions are subject to partial deductions escalating by weekly increments.",
    "Official university transcripts, degree verification records, and duplicate grade sheets can be requested through the digital registrar service portal. Processing durations typically range from three to seven business days for standard electronic deliveries, while expedited physical postal dispatch requires supplemental courier fee payment. Graduating students must secure clear financial clearances from library, laboratory, and hostel divisions before transcript release.",
    "Campus healthcare services are administered via the university central medical dispensary, providing round-the-clock primary clinical triage, outpatient consultations, and prescription medication dispensations. In the event of acute emergencies or conditions requiring specialized tertiary care, campus ambulance units transfer patients to designated network teaching hospitals under institutional student insurance coverage.",
    "Inter-campus bus transit schedules operate continuously on twenty-minute departure loops connecting academic halls, engineering laboratory complexes, sports stadiums, and university residential hostels. Students must present active digital smart identification cards when boarding campus transit shuttles. Periodic route adjustments during examination terms and institutional recess periods are broadcast through mobile notifications.",
    "Degree audit clearances and graduation application checklists must be finalized by prospective graduating candidates during the semester immediately preceding their anticipated commencement date. Departmental academic advisors review fulfilled core curriculum requirements, elective distributional credits, and mandatory internship hours to confirm comprehensive degree eligibility before registrar graduation approval.",
    "Library circulation policies permit enrolled undergraduate students to borrow up to five standard curriculum volumes simultaneously for an initial lending window of fourteen calendar days. Renewable borrowing privileges are granted online provided no active recall reservation has been lodged by another student or faculty member. Late book returns incur per-diem administrative overdue fines capped at replacement catalog values.",
    "The university student grievance redressal committee provides a formal structured appellate mechanism to address academic irregularities, unfair evaluation allegations, and harassment complaints. Grievances must be lodged within ten business days of disputed incidents or result publications. Confidential hearings are scheduled within two calendar weeks, guaranteeing due process and objective inquiry proceedings.",
    "Laboratory safety protocols mandate that personal protective equipment including approved lab coats, eye protection goggles, and closed-toe footwear must be worn during all experimental sessions. Hazardous chemical wastes must be segregated according to compatibility categories and placed in designated disposal carboys. Failure to adhere to basic laboratory safety directives results in immediate suspension of practical facility privileges.",
    "Undergraduate research grants and project innovation funds are awarded on a competitive proposal basis through the university scientific research board. Awarded capital grants cover specialized consumable laboratory reagents, conference dissemination travel stipends, and research publication charges. Grantees are required to submit interim progress reports and final project deliverables within twelve months of disbursement.",
    "Student exchange and bilateral study abroad programs enable qualified sophomore and junior scholars to complete up to two semesters of academic study at partner institutions internationally. Academic credit transfers are coordinated through pre-approved course equivalence agreements certified by the respective academic dean. Participants must maintain minimum GPA standing and zero disciplinary infractions.",
    "Continuous internal assessment mechanisms comprise periodic unannounced quizzes, midterm evaluations, collaborative group assignments, and laboratory practical assessments. Faculty instructors must publish assessment weightings and scheduled deliverable due dates on the learning management system within the opening fortnight of class instruction. Late assignment submissions without verified medical excuses incur ten percent penalties daily.",
    "Disciplinary procedures regarding academic integrity strictly penalize acts of plagiarism, unauthorized collaboration, and examination cheating. Suspected violations are forwarded to the academic integrity board for formal adjudication. Sanctions range from mandatory assignment resubmission with grade penalty caps to disciplinary suspension or permanent academic expulsion depending on infraction severity.",
    "Campus parking regulations require all motor vehicles operated by commuting students to display authorized university registration permits on front windshields. Vehicle operations within academic zones are restricted to designated speed limits, and parking is authorized only within demarcated peripheral lots. Unauthorized vehicular parking in faculty bays results in monetary towing fines.",
    "Career services and corporate relations units organize on-campus recruitment cycles, industry internship placement fairs, and resume enhancement workshops for graduating classes. Eligibility criteria for specific campus recruitment drives are determined independently by visiting enterprise partners based on cumulative grade cutoffs, domain specialization tracks, and test performance.",
    "Financial aid and institutional merit scholarship opportunities are reviewed annually based on academic excellence, sports achievements, or demonstrated socioeconomic financial need. Application forms must be submitted alongside certified parental income tax documentation before the published scholarship deadline. Awardees must maintain minimum semester grade thresholds to guarantee scholarship continuation.",
    "Information technology acceptable use policies mandate that university network infrastructure, wireless local area networks, and server systems be utilized exclusively for lawful academic and administrative endeavors. Peer-to-peer torrent downloads, unauthorized network scanning, and transmission of copyrighted multimedia are rigorously prohibited and result in permanent network access revocations.",
    "Student union elections and campus representative governance bodies operate according to student constitution bylaws overseen by an independent faculty election commissioner. Candidates must possess good academic standing, no history of disciplinary probation, and zero pending criminal actions. Campaign expenditures are strictly capped to ensure equitable competitive electoral opportunities.",
    "The office of international student services assists foreign students with visa compliance renewals, local residential registration formalities, and cultural integration programming. International scholars are advised to maintain continuous full-time enrollment status and report any domestic residential address modifications within fourteen calendar days to satisfy legal visa oversight mandates.",
    "Undergraduate research capstone and senior design thesis projects must be executed under the direct guidance of an assigned departmental faculty supervisor. Comprehensive project reports must adhere to standard institutional formatting guidelines and pass similarity index checks below fifteen percent. Final project evaluations include public oral defenses before examination committees.",
    "Campus athletic facilities, including the olympic gymnasium, indoor badminton complexes, and aquatic centers, are accessible to all verified students possessing valid recreation memberships. Users must comply with facility dress codes and adhere to safety rules posted across specific activity sectors. University sports team trials are conducted annually during the autumn semester.",
    "Academic credit transfer and lateral entry evaluations are processed through the university equivalency appraisal committee upon submission of official syllabus catalogs and certified transcripts. A maximum of sixty transferable credits may be counted toward graduation requirements. Grades earned at external institutions do not factor into the university cumulative grade point calculation.",
    "Student mental health counseling and psychological wellness centers provide free confidential psychological support, stress management counseling, and cognitive behavioral workshops for students experiencing anxiety or distress. Licensed mental health practitioners maintain total client confidentiality in accordance with professional ethical codes and statutory patient privacy mandates.",
    "Campus food services and residential dining halls operate under strict hygiene audits, hazard analysis, and nutritional balance guidelines monitored by student mess supervision committees. Caterers must display weekly rotational dietary menus and accommodate allergen-free nutritional requirements. Unsanitary food handling practices trigger immediate contractual termination penalties.",
    "Environmental sustainability and green campus initiatives prohibit single-use disposable plastics within all commercial university premises. Solid waste segregation into compostable organic, recyclable dry, and hazardous electronic categories is enforced across all academic buildings. Campus tree plantation campaigns and energy conservation drives are led by student eco-clubs.",
    "Intellectual property management regulations dictate ownership rights regarding inventions, software innovations, and patentable discoveries produced during university-sponsored research programs. Inventions created using substantial institutional infrastructure are jointly patented with the university, with commercial licensing royalties distributed equitably between inventors and research support funds.",
    "Emergency response protocols and campus evacuation procedures are rehearsed biannually through coordinated fire drills and safety simulations. Emergency assembly muster points are marked adjacent to all academic complexes, and students must heed siren instructions and instructions from designated floor fire wardens without attempting to retrieve personal possessions.",
    "Auditing and non-credit course participation permissions allow students to attend designated lecture modules without completing formal graded examinations or earning graduation degree credits. Instructor approval is mandatory, and course registrations are approved solely on an available seating space basis after regular degree-seeking student enrollment concludes.",
    "Alumni association engagement networks foster sustained connections between past graduates and the institutional community through mentorship schemes, guest lecture series, and endowment funding campaigns. Graduating alumni receive lifetime access to regional chapter networking events, university library digital archives, and institutional employment bulletin boards.",
    "Continuing professional education and lifelong learning certificates are administered through evening executive education and distance learning platforms. Modular curriculum certifications require completion of designated competencies evaluated through capstone assignments and remote proctored examinations before recognized digital credentials are authenticated.",
]


def run_benchmark(
    model_name: str = "intfloat/multilingual-e5-small",
    iterations: int = 50,
    warmups: int = 10,
    batch_size: int = 32,
):
    print(f"\n=======================================================")
    print(f"UniMind Embedding Pipeline Benchmark: {model_name}")
    print(f"Passages: {len(SYNTHETIC_32_CHUNKS)} chunks (~150 tokens/chunk)")
    print(f"Warm-up: {warmups} runs | Timed: {iterations} runs | Batch Size: {batch_size}")
    print(f"=======================================================")

    process = psutil.Process(os.getpid())
    rss_start = process.memory_info().rss / (1024 * 1024)

    # 1. Cold-start model loading measurement
    t_load_start = time.perf_counter()
    embedder = DenseEmbedder(model_name=model_name, use_mock=False)
    t_load_end = time.perf_counter()
    cold_load_time_ms = (t_load_end - t_load_start) * 1000

    rss_after_load = process.memory_info().rss / (1024 * 1024)
    model_rss_delta = rss_after_load - rss_start

    # Count tokens in benchmark suite
    tokenizer = embedder.model.tokenizer
    token_counts = [len(tokenizer.encode(p, add_special_tokens=False)) for p in SYNTHETIC_32_CHUNKS]
    total_tokens = sum(token_counts)
    avg_tokens_per_chunk = total_tokens / len(SYNTHETIC_32_CHUNKS)

    print(f"Cold Model Load Time: {cold_load_time_ms:.2f} ms")
    print(f"Base RSS: {rss_start:.2f} MB -> Post-Load RSS: {rss_after_load:.2f} MB (Model Weight RSS: +{model_rss_delta:.2f} MB)")
    print(f"Total Corpus Tokens: {total_tokens} (Mean per chunk: {avg_tokens_per_chunk:.1f} tokens)")

    # 2. Warm-up iterations
    print(f"\nExecuting {warmups} warm-up iterations...")
    for _ in range(warmups):
        _ = embedder.encode_passages(SYNTHETIC_32_CHUNKS, batch_size=batch_size)

    # 3. Timed benchmark iterations with tracemalloc
    tracemalloc.start()
    print(f"Executing {iterations} timed benchmark iterations...")
    latencies = []
    t_bench_start = time.perf_counter()

    for _ in range(iterations):
        t_iter_start = time.perf_counter()
        matrix = embedder.encode_passages(SYNTHETIC_32_CHUNKS, batch_size=batch_size)
        latencies.append((time.perf_counter() - t_iter_start) * 1000)

    t_bench_end = time.perf_counter()
    total_timed_duration = t_bench_end - t_bench_start

    current_heap, peak_heap = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    rss_end = process.memory_info().rss / (1024 * 1024)
    inference_rss_delta = rss_end - rss_after_load

    # Validation check on output
    assert matrix.shape == (len(SYNTHETIC_32_CHUNKS), 384), f"Unexpected shape {matrix.shape}"
    assert matrix.dtype == np.float32, f"Unexpected dtype {matrix.dtype}"

    # Compute statistics
    mean_latency = float(np.mean(latencies))
    p50_latency = float(np.percentile(latencies, 50))
    p95_latency = float(np.percentile(latencies, 95))
    min_latency = float(np.min(latencies))
    max_latency = float(np.max(latencies))

    total_chunks_processed = iterations * len(SYNTHETIC_32_CHUNKS)
    total_tokens_processed = iterations * total_tokens
    chunks_per_sec = total_chunks_processed / total_timed_duration
    tokens_per_sec = total_tokens_processed / total_timed_duration

    print("\n--- Empirical Benchmark Results ---")
    print(f"Cold-Start Model Load:   {cold_load_time_ms:.2f} ms")
    print(f"Warm Inference Mean:     {mean_latency:.2f} ms per 32 chunks")
    print(f"Warm Inference P50:      {p50_latency:.2f} ms")
    print(f"Warm Inference P95:      {p95_latency:.2f} ms")
    print(f"Warm Inference Min/Max:  {min_latency:.2f} ms / {max_latency:.2f} ms")
    print(f"Throughput (Chunks):     {chunks_per_sec:.2f} chunks/sec")
    print(f"Throughput (Tokens):     {tokens_per_sec:.2f} tokens/sec")
    print(f"Python Heap Peak:        {peak_heap / (1024 * 1024):.2f} MB")
    print(f"Process RSS (Start):     {rss_start:.2f} MB")
    print(f"Process RSS (Post-Load): {rss_after_load:.2f} MB (Delta: +{model_rss_delta:.2f} MB)")
    print(f"Process RSS (Final):     {rss_end:.2f} MB (Inference Delta: +{inference_rss_delta:.2f} MB)")
    print("-----------------------------------\n")

    return {
        "model": model_name,
        "cold_load_ms": round(cold_load_time_ms, 2),
        "mean_latency_ms": round(mean_latency, 2),
        "p50_latency_ms": round(p50_latency, 2),
        "p95_latency_ms": round(p95_latency, 2),
        "min_latency_ms": round(min_latency, 2),
        "max_latency_ms": round(max_latency, 2),
        "chunks_per_sec": round(chunks_per_sec, 2),
        "tokens_per_sec": round(tokens_per_sec, 2),
        "peak_heap_mb": round(peak_heap / (1024 * 1024), 2),
        "model_rss_mb": round(model_rss_delta, 2),
        "total_rss_mb": round(rss_end, 2),
    }


if __name__ == "__main__":
    run_benchmark(
        model_name="intfloat/multilingual-e5-small",
        iterations=50,
        warmups=10,
        batch_size=32,
    )
