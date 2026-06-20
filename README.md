# Self-Healing Data Pipeline

When an incoming CSV's columns drift, a local LLM maps the drifted names back to the expected schema instead of crashing. The strict schema is the **external verifier** — the model proposes a mapping, the schema decides whether it ships.

Runs fully locally on [Ollama](https://ollama.com).

## Stack

| Piece | Choice |
|-------|--------|
| Data | pandas |
| LLM runtime | Ollama (local) |
| Model | `phi3` (configurable) |
| Transport | requests (`format=json`) |

## Setup

```bash
ollama pull phi3
pip install -r requirements.txt
```

## Usage

```bash
python pipeline.py        # runs the built-in demo with drifted columns
```

Configure via env vars: `OLLAMA_MODEL`, `OLLAMA_URL`.

In your own code:

```python
from pipeline import process_data, EXPECTED_SCHEMA
clean = process_data(my_dataframe, EXPECTED_SCHEMA)
```

## Test

```bash
pip install pytest
pytest        # LLM call is monkeypatched — no network needed
```

## Limitations

- The LLM can mis-map semantically similar columns; for critical data it should **propose**, not auto-apply.
- `format=json` reduces parse failures but doesn't eliminate them.

---

Inspired by Aman Kharwal's tutorial, [Implementing a Self-Healing Data Pipeline](https://amanxai.com/2026/05/27/implementing-a-self-healing-data-pipeline/). Rebuilt and extended (fast path, hard verification gate, alerting, env config).

MIT licensed.
