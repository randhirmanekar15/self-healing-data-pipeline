# Your Data Pipeline Shouldn't Die Because Someone Renamed a Column

*I built a pipeline that reads a broken CSV, figures out what the columns *should* be, and fixes itself — no 2 a.m. pager alert required.*

## Why this, why now

Most pipeline failures aren't dramatic. They're a vendor quietly renaming `transaction_id` to `txn_id`, and your ETL job exploding on a `KeyError` at 2 a.m. while you sleep.

In 2026, this is exactly the problem everyone's pointing AI agents at. The interesting work has moved out of chatbots and into operations — data engineering, infra, ops — and "reliability" is the word doing all the heavy lifting. Gartner's 2026 Hype Cycle for Agentic AI puts governance and reliability right next to raw capability, which tells you where the maturity conversation actually is: not "can it do the task" but "can I trust it to not make things worse."

One caveat I'll put up front, because the research is clear on it: LLM self-correction is only reliable when there's an **external verifier**. A model left to grade its own homework drifts. In this build, the strict schema *is* the verifier. The LLM proposes a mapping; the schema decides whether it's allowed to ship. That distinction is the whole reason this works.

## What it does

The pipeline expects four columns:

`transaction_id`, `customer_email`, `purchase_amount`, `purchase_date`.

A new file shows up with `txn_id`, `email_address`, `total_cost`, `date`. A normal pipeline crashes here.

Mine notices the mismatch, asks a local LLM to map the drifted names to the expected ones by *meaning*, renames the columns, and verifies nothing is missing before letting the data through. If it can't fully heal the schema, it doesn't guess — it raises and alerts.

## The stack

| Layer | Tool | Why |
|---|---|---|
| Language | Python | pandas is still the fastest path for tabular work |
| Data | pandas | `df.rename()` does the actual healing |
| LLM runtime | Ollama (local) | No API keys, no per-token cost, data never leaves the machine |
| Model | phi3 | Small, fast, already on my laptop — good enough for a mapping task |
| Transport | requests | Plain HTTP POST to the local Ollama endpoint |

## How it works

The healing step asks the model to return a strict JSON mapping. I force `format="json"` so I'm not regex-scraping prose out of a response.

```python
import requests, json

def heal_schema(expected_cols, actual_cols):
    prompt = (
        "Map each actual column to the correct expected column by semantic meaning.\n"
        f"Expected: {expected_cols}\n"
        f"Actual: {actual_cols}\n"
        "Return ONLY a JSON object: {actual_column: expected_column}."
    )
    resp = requests.post(
        "http://localhost:11434/api/generate",
        json={"model": "phi3", "prompt": prompt, "format": "json", "stream": False},
        timeout=30,
    )
    return json.loads(resp.json()["response"])
```

The orchestration is where I keep the LLM on a short leash. Match the schema? Skip the model entirely. Mismatch? Heal, rename, then **verify** — and refuse to pass partially-fixed data.

```python
def process_data(df, expected_schema):
    if list(df.columns) == expected_schema:
        return df  # fast path — never call the LLM when you don't need to

    mapping = heal_schema(expected_schema, list(df.columns))
    df = df.rename(columns=mapping)

    missing = [c for c in expected_schema if c not in df.columns]
    if missing:
        alert(f"Unrecoverable schema drift. Still missing: {missing}")
        raise ValueError(f"Schema healing failed: {missing}")

    return df[expected_schema]
```

The `missing` check is the verifier. The LLM gets to *suggest*. It never gets to *decide* whether the data is good.

## What I changed from the tutorial

Aman Kharwal's original is a clean proof of concept. I made four changes to get it closer to something I'd actually run:

1. **Swapped the model to one already on my machine.** No new pull, no extra GB. phi3 handles a four-column mapping fine — you don't need a frontier model to recognize that `total_cost` means `purchase_amount`.
2. **Added an explicit fast path.** If columns already match, I return immediately and never hit the LLM. The healthy case stays free and deterministic. You only pay the model tax when something's actually broken.
3. **Made verification a hard gate.** The original trusts the rename. I diff against the expected schema afterward and refuse partial fixes — a half-healed frame is worse than a clean crash.
4. **Added alerting on unrecoverable drift.** When healing fails, it logs the exact missing columns and fires an alert before raising. That turns a silent failure into an actionable one.

## Where it breaks

I'd be lying if I called this production-grade for anything critical.

The LLM can mis-map. `date` is obvious; two columns named `amount` and `value` are not, and the model might confidently pick wrong. For financial data, a confident wrong answer is the worst outcome.

`format="json"` reduces parse failures but doesn't eliminate them — a malformed response still needs a try/except and a fallback path.

And the honest limit: this should *propose* fixes on critical pipelines, not auto-apply them. Self-healing on a logging table is great. Self-healing on a payments table without a human in the loop is how you reconcile the wrong numbers for a quarter.

## Takeaway

Self-healing isn't magic and it isn't "let the LLM run the pipeline." It's a small model doing one narrow job — proposing a column mapping — behind a strict verifier that has final say.

That pattern generalizes. Anywhere you have a clear notion of "correct," you can let an LLM attempt the fix and let the rule decide whether it ships.

*Built on and credited to Aman Kharwal's [Implementing a Self-Healing Data Pipeline](https://amanxai.com/2026/05/27/implementing-a-self-healing-data-pipeline/) — I adapted his approach with my own model choice, fast path, verification gate, and alerting.*

### Sources
- [Aman Kharwal — Implementing a Self-Healing Data Pipeline](https://amanxai.com/2026/05/27/implementing-a-self-healing-data-pipeline/)
- [Gartner — Hype Cycle for Agentic AI](https://www.gartner.com/en/articles/hype-cycle-for-agentic-ai)
- [Self-healing systems with LLMs (arXiv)](https://arxiv.org/abs/2605.06737)
