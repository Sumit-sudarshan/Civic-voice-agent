# Civic Voice Agent: Design & Evaluation Write-up

## 1. How I designed the agent pipeline

The system ingests citizen complaints and suggestions in English, Hindi, or Marathi, and turns them into categorized, urgency-ranked records on a dashboard for a local leader (MLA, corporator, panchayat head).

The core design decision was to decompose the work into a directed pipeline of small LLM calls instead of one large call that "processes the complaint." Each call either selects one label from a closed set or fills a fixed group of fields. This keeps the reasoning burden per call small enough for a 1.5B model to handle reliably, isolates failure to a single stage, and gives every stage a contract that can be measured independently.

The pipeline runs in two parts with different latency requirements:

- **Conversation loop** (synchronous, citizen is waiting): language detection, optional translation to English, a gatekeeper call that triages the message into one of seven categories (valid complaint, valid suggestion, spam/gibberish, off-topic, unactionably vague, abusive, or personal emergency), and a dialogue manager that asks for missing details. The LLM only reads the transcript and proposes the next question; a deterministic state machine enforces re-ask limits, validates the model's claims (e.g., rejecting a pincode that isn't 6 digits), and catches known small-model failures such as echoing a street address into the area field. Any LLM failure here falls back to a static question so the conversation never dead-ends.
- **Finalize pipeline** (asynchronous, runs after the citizen has confirmation): classify into one of 8 categories, assess urgency with a rationale, extract structured fields (location, issue, affected parties, ask), embed the text, and deduplicate against recent records in the same category and area. A stage that exhausts its retries doesn't discard the submission: the record is committed with a `needs_human_review` flag and reason logged, rather than discarded, so a failure is contained to one item. (This flag is persisted and available via the API, but there is currently no dashboard view or workflow for a leader to act on it, it's inspectable in the database/eval tooling only.)

The governing principle across both loops is that the LLM proposes and deterministic Python code disposes: every model output is validated against a Pydantic schema with bounded retry before it can touch persisted state, and control flow (retries, state transitions, merge/create decisions) is never delegated to the model itself.

## 2. Which open-source LLM(s) I chose and why

All reasoning uses open-source models behind a single client interface, with the backend selected by a single environment variable so every prompt runs unmodified on either:

- **Qwen2.5 1.5B (local, via Ollama, CPU)**: the default backend. It runs on commodity hardware at zero marginal cost, and because the pipeline never asks it for open-ended reasoning, only closed-set classification or fixed-schema extraction, a model this small stays viable.
- **Llama 3.1 8B Instant (hosted, via Groq)**: an optional backend for when stronger judgment is needed, particularly on urgency assessment, AI reasoning and non-English/Hinglish input, where the 1.5B model's capacity is partly consumed by cross-lingual handling.
- **nomic-embed-text (local, via Ollama)**: used for deduplication embeddings. This is always local regardless of which reasoning backend is selected, since Groq exposes no embeddings endpoint and dedup vectors are derived from PII-bearing text.
- **IndicTrans2 dist-200M (local, CPU)**: normalizes Hindi/Marathi input to English before downstream reasoning. Translation is optional: if the model isn't available, text passes through untranslated and prompts are written to tolerate mixed-script input.


## 3. How I collected and structured test data

Roughly 1,100 candidate cases were drafted, largely LLM-assisted, with expected labels for the gatekeeper/category/urgency/dedup outcomes, split across dataset files by what they test:
- 800 category/urgency cases covering the ordinary distribution of complaint types.
- 200 adversarial edge cases (vague messages, rants, off-topic input, tone-vs-content conflicts, e.g. an abusive rant that still contains a genuine grievance).
- 100 deduplication pairs, including authored hard negatives (same locality and topic, but a materially different underlying problem), to stress-test merge precision rather than let a "merge everything" policy score well on recall alone.
- 15 multilingual cases (Hindi/Marathi) to check the translation-and-classify path.

Not all 1,100 have been human-verified. Human effort so far has gone into two places: a 45-case core subset, drawn from across the categories above and checked by hand, which is what the harness actually runs on every prompt-iteration round (minutes on CPU); and a separate 19-case extraction set, scored by hand across 4 fields each for the human rubric. The remaining 800/200/100/15 case files exist as drafted ground truth with LLM-assigned expected labels, sitting behind a "full suite" flag in the harness that hasn't yet been run or human-verified at that scale due to time constraints.

## 4. Evaluation approach and results

Different pipeline outputs have different epistemics: some have exactly one right answer, some have a right set, some have no single canonical answer. So a single metric across all of them would misrepresent quality. Four evaluation mechanisms are matched to each output type:

- **Ground-truth scoring** (gatekeeper, classify, urgency): accuracy plus per-label precision/recall/F1 with confusion matrices. These three stages each have a single defensible correct label per case, so a straightforward accuracy comparison against ground truth felt like the right fit here.
- **Pairwise set comparison** (deduplication): precision/recall of predicted duplicate pairs against authored ground-truth pairs, using the hard negatives to ensure precision is genuinely tested and the hard negatives specifically guard against a lenient threshold.
- **Human rubric with an LLM judge as a validated proxy** (extraction): a 1–5 human rubric across 19 cases × 4 fields; the LLM judge is only reported alongside the human scores after demonstrating 83% within-one-point agreement with them, and is never treated as a replacement. Extraction doesn't have one canonical correct answer the way classification does, so a rubric felt more honest than an exact-match score.
- **Blind reader test with a scoped hallucination check** (leader briefing): the rendered briefing is handed to a fresh, stateless model role-playing a busy leader, and its answers to five concrete operational questions(total_issues, critical_count, top_category, most_affected_area and top_priority_location) are checked deterministically in code against the ground-truth figures. A separate, narrowly scoped call fact-checks the one generated sentence in the briefing. The reasoning here was that what actually matters is whether a leader could correctly understand and act on the briefing, so testing comprehension directly seemed more meaningful than scoring the writing itself.

Headline results on the core suite, same cases on both backends (local → hosted):
- Gatekeeper accuracy: 82.2% → 86.7%
- Category accuracy: 76% → 88%
- Urgency within-one-level accuracy: 92% → 96%
- Dedup precision: 1.00 on both backends; recall 0.89
- Multilingual category accuracy: 100% (hosted)

The evaluation harness calls the same client and prompts as production, so these numbers describe the deployed system rather than a separate lab replica.

## 5. What I would improve with more time


- Replace self-judging on extraction with an independent judge model, or demote the current LLM judge to a triage role that routes low-confidence scores to a human.
- Do targeted few-shot repair aimed at the specific confusions the confusion matrices expose (e.g., safety vs. roads), rather than general prompt tuning.
- Expand multilingual testing well beyond the current 15 cases, particularly for abuse and emergency detection in Hindi and Marathi, which is untested relative to category classification.
- Human-verify the remaining ~1,050 drafted cases and run the full suite (rather than the 45-case core subset) on both backends for final release-grade numbers.
- Wire feedback capture into evaluation: Use the captured citizen confirmations and leader corrections to build a real-world ground-truth dataset instead of relying only on synthetic/drafted data.
- Investigate deduplication recall: Precision is perfect (1.00) but recall is 0.89. A dedicated pass is needed to analyze why duplicates are missed (e.g., threshold limits or paraphrasing issues).
- Develop an automated extraction metric: Build a purpose-built extraction metric instead of a human rubric alone. I deliberately ruled out BLEU/ROUGE/BERTScore since they require a single reference answer. With more time, I would design a scoring method focused specifically on factual correctness rather than continuing to rely on a small hand-scored rubric.


## 6. How long I spent

The work ran over roughly a week, totaling 45 to 55 hours. Started with the documentation, a few hours went to initial design and architecture. Then some hours for implementing the code. Substantial time was spent on building and refining pipeline stages and prompts. Another substantial block was spent on evaluation harness and testing. The remainder went to building the synthetic dataset , running iterative debug runs and testing the full system.



## What I am not building (and why)

This is a demo focused on the AI pipeline and its evaluation, not a finished production system. The points below are a condensed summary; see [what_i_am_not_building.md] for the full write-up of what was deliberately left out, why, and what a production version would need.

- **Login and accounts.** Citizen login is unauthenticated browser session state, and the leader dashboard has no auth. Authentication was left out because it is a standard, solved engineering problem, so time was prioritized on core AI pipeline mechanics and evaluation. A production deployment would use phone OTP authentication for citizens and role-based, area-scoped logins for municipal leaders.
- **Assigning the responsible official by area.** All complaints land on a single dashboard without routing to specific ward officers. This was left out because it requires complex administrative jurisdiction maps linking areas and categories to officers, which is an administrative data task separate from AI engineering. Production needs spatial and categorical mapping to automatically dispatch complaints to designated officials.
- **Rate limiting.** No submission throttles or IP/device limits exist on the API endpoints. Submission caps were omitted because traffic volume was negligible during local development and offline evaluation. A production system would implement per-phone-number and per-email rate limiting to prevent spam floods without penalizing public shared networks.
- **Blocking abuse and fake reports.** Protection relies solely on single-message LLM gatekeeping without anti-bot or coordinated flood detection. Behavioral traffic analytics and bot mitigation require real-world telemetry outside an LLM pipeline scope. Production would integrate CAPTCHA, bot detection heuristics, and cluster analysis to catch coordinated fake campaigns.
- **Protecting citizen data.** Citizen PII (names, phone numbers, addresses) is stored in plaintext across database tables and logs. PII was kept unmasked intentionally to visually audit extractions, verify location matching, and score deduplication accuracy. A production build requires field-level encryption, masked dashboard views, and clear data retention policies.
- **Handling infrastructure scale.** The backend runs on a single local model instance, SQLite, and in-memory FastAPI background tasks. Lightweight local components were chosen for zero-cost execution and simple setup during prototyping. Production would replace these with a relational database like Postgres, distributed queues like Redis/Celery, and scalable model workers.
- **Operational cost control.** No live budget tracking or per-request cost controls are implemented across LLM providers. Small evaluation volumes made live financial monitoring unnecessary, though the hybrid design already supports local offloading. A real system should dynamically route simple pipeline steps locally and reserve hosted LLMs for complex cases.
- **Pipeline failure monitoring.** Stage errors rely on database review flags (`needs_human_review`) or manual log inspection. Internal DB flags and logs were sufficient for developer analysis during pipeline construction. Production needs real-time observability dashboards (e.g., Grafana/Prometheus) and automated alerting for pipeline errors.
- **Automated workflow escalation.** Status tracking is manual, with no auto-routing or SLA escalation for unresolved tickets. Workflow management sits on top of the backend API rather than within the core LLM intelligence layer. Production requires automated SLA escalation triggers and departmental task routing upon complaint ingestion.
- **Alternative evaluation metrics (Confidence & BLEU/ROUGE).** Model confidence scores and BLEU/ROUGE metrics were explicitly excluded. Small LLM confidence scores are uncalibrated and unreliable, while BLEU/ROUGE measure word overlap rather than factual precision. Production evaluation should focus on schema enforcement, programmatic unit checks, and factual accuracy metrics.
- **Voice input & Speech-to-Text.** Intake is text-based only, with no integrated speech-to-text pipeline step. Speech recognition across diverse Indian accents and noisy audio is a distinct domain requiring separate model tuning. It is not addressed due to time constraints. A production version would add a dedicated Whisper/IndicASR pre-processing layer that feeds transcribed text into the current pipeline unchanged.
- **Multilingual safety and moderation scope.** Safety/moderation gatekeeping in Hindi and Marathi was not exhaustively evaluated. Benchmark focus was directed at Indic category classification, which accounts for the vast majority of operational pipeline traffic. Production requires dedicated Indic safety test suites targeting regional abuse variations, slurs, and emergency phrasing.


