# Self-Healing Data Pipeline

![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue) ![License: MIT](https://img.shields.io/badge/License-MIT-green) ![Runs 100% Local](https://img.shields.io/badge/runs-100%25%20local-orange)

**When an incoming CSV's columns drift, a local LLM maps the drifted names back to the expected schema instead of crashing.**

## Overview

Data pipelines break for the dumbest reason: someone upstream renamed `customer_id` to `cust_id` and your nightly job dies at 3 a.m. The traditional fix is a brittle rename map that you patch every time it breaks. This project takes a different bet — let a local LLM propose the column mapping, and let your strict schema decide whether that mapping is allowed to ship.

Reliability and "self-healing" are the defining infrastructure themes of 2026. But self-correction only works when there's something outside the model that can say *no*. An LLM left to grade its own homework will happily hallucinate a fix and mark it correct. Here the schema is the external verifier: the LLM proposes, the schema disposes. If the proposed mapping doesn't produce every required column, the heal is rejected — no partial fixes, no silent corruption.

It's also deliberately cheap. When the incoming columns already match the expected schema (the common case), the pipeline never touches the LLM at all — a fast path skips straight to processing. The model is only invoked when there's real drift to repair, and even then it runs entirely on your machine via [Ollama](https://ollama.com/). No data leaves the box.

## Features

- **Schema-match fast path** — identical columns skip the LLM entirely. Zero latency, zero tokens on the happy path.
- **Strict verification gate** — the schema is the verifier. A heal ships only if it reproduces *every* required column. Partial fixes are refused, not patched in.
- **Local LLM healing** — drifted column names are mapped back via `phi3` on Ollama with `format=json` for a clean, parseable mapping.
- **Alerting hook** — unrecoverable drift fires an alert instead of crashing or silently dropping rows.
- **100% local** — no API keys, no cloud, no data exfiltration.
- **Env-based config** — point at any Ollama model or host without touching code.
- **Tested without a GPU** — the LLM call is monkeypatched in tests, so the verification logic runs in CI with no model required.

## How it works

An incoming DataFrame is checked against the expected schema. If columns already match, it ships immediately. Only on a mismatch does the pipeline call the local LLM to propose a `{drifted_name: expected_name}` mapping. That mapping is then applied and **re-verified against the schema** — if and only if all required columns are present does the data ship. Anything else triggers an alert.

```text
                 incoming df
                      │
                      ▼
            ┌───────────────────┐
            │ columns == schema? │
            └───────────────────┘
               │            │
            yes│            │no
               │            ▼
               │     ┌──────────────┐
               │     │ heal via LLM │  (Ollama / phi3, format=json)
               │     │ propose map  │
               │     └──────────────┘
               │            │
               │            ▼
               │     ┌──────────────┐
               └────►│   VERIFY      │  ← schema is the external verifier
                     │ all cols ok?  │
                     └──────────────┘
                       │          │
                    pass│          │fail
                       ▼          ▼
                    ┌──────┐   ┌────────┐
                    │ SHIP │   │ ALERT  │
                    └──────┘   └────────┘
```

The verifier is the whole point: the LLM is never trusted to confirm its own fix. The schema does.

## Tech stack

| Component | Choice | Why |
|-----------|--------|-----|
| Data handling | **pandas** | DataFrame in, DataFrame out |
| LLM runtime | **Ollama** (local) | No keys, no cloud, no egress |
| Model | **phi3** | Small, fast, good enough for column mapping |
| Output format | `format=json` | Clean, parseable mapping with fewer parse failures |
| Transport | **requests** | Plain HTTP call to the Ollama endpoint |
| Language | **Python 3.10+** | — |

## Project structure

```text
self-healing-data-pipeline/
├── pipeline.py        # heal_schema() + process_data() + a runnable demo
├── test_pipeline.py   # tests with the LLM call monkeypatched
├── ARTICLE.md         # source-tutorial credit and what I changed
├── requirements.txt
├── LICENSE            # MIT
└── README.md
```

## Installation

```bash
# 1. Clone
git clone https://github.com/randhirmanekar15/self-healing-data-pipeline.git
cd self-healing-data-pipeline

# 2. Install Python deps
pip install -r requirements.txt

# 3. Install Ollama and pull the model (https://ollama.com/download)
ollama pull phi3
ollama serve   # if not already running
```

## Usage

Run the built-in demo, which feeds the pipeline a DataFrame with drifted column names and watches it heal:

```bash
python pipeline.py
```

Use it in your own code by importing `process_data` and handing it your DataFrame plus the schema you expect:

```python
from pipeline import process_data, EXPECTED_SCHEMA

shipped_df = process_data(incoming_df, EXPECTED_SCHEMA)
# matches schema  -> returned as-is (fast path)
# drift, healable -> columns remapped, verified, returned
# drift, unrecoverable -> alert fires, no partial data ships
```

## Configuration

| Env var | Default | Description |
|---------|---------|-------------|
| `OLLAMA_MODEL` | `phi3` | Model used to propose the column mapping |
| `OLLAMA_URL` | `http://localhost:11434/api/generate` | Ollama generate endpoint |

## Testing

The LLM call is monkeypatched, so the suite verifies the fast path, the healing logic, and the verification gate **without needing Ollama or a GPU**:

```bash
pip install pytest
pytest
```

## Limitations

- **Semantic near-misses.** The LLM can mis-map columns that look similar (`net_amount` vs `gross_amount`). For critical data the model should *propose* a mapping for human review, not auto-apply it.
- **Parse failures.** `format=json` reduces malformed output but doesn't eliminate it. The verifier catches bad results, but a failed parse still means a failed heal.
- **Small-model ceiling.** `phi3` is fast and local but less capable than a frontier model on ambiguous or many-column schemas.
- **Mapping only.** This heals column *names*, not type drift, unit changes, or value-level corruption.

## Roadmap

- [ ] Propose-don't-apply mode with a human approval step for critical schemas
- [ ] Confidence score per mapping; auto-apply only above a threshold
- [ ] Type and dtype verification in the schema gate, not just column names
- [ ] Pluggable alert sinks (Slack, email, webhook)
- [ ] Retry-with-feedback loop: pass the verifier's rejection reason back to the LLM

## Credits

📖 Full write-up: [ARTICLE.md](ARTICLE.md).

Based on Aman Kharwal's tutorial, ["Implementing a Self-Healing Data Pipeline"](https://amanxai.com/2026/05/27/implementing-a-self-healing-data-pipeline/).

**What I changed vs the source tutorial:**

- **Schema-match fast path** — skip the LLM entirely when columns already match.
- **Hard verification gate** — the schema verifies every heal and refuses partial fixes.
- **Alerting hook** — unrecoverable drift raises an alert instead of failing silently.
- **Env-based config** — `OLLAMA_MODEL` and `OLLAMA_URL` instead of hardcoded values.

## Author

Built by **Randhir Manekar** — [randhirmanekar.com](https://randhirmanekar.com) · [github.com/randhirmanekar15](https://github.com/randhirmanekar15)

## License

MIT — see [LICENSE](LICENSE).
