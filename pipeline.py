"""Self-healing data pipeline.

When an incoming CSV's columns drift (a vendor renames `transaction_id` to
`txn_id`), a local LLM maps the drifted names back to the expected schema instead
of crashing. The strict schema is the external verifier: the model proposes a
mapping, the schema decides whether it is allowed to ship.

Inspired by Aman Kharwal's tutorial:
https://amanxai.com/2026/05/27/implementing-a-self-healing-data-pipeline/
"""

from __future__ import annotations

import json
import os
import sys

import pandas as pd
import requests

MODEL = os.environ.get("OLLAMA_MODEL", "phi3")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
REQUEST_TIMEOUT = 30  # seconds

EXPECTED_SCHEMA = [
    "transaction_id",
    "customer_email",
    "purchase_amount",
    "purchase_date",
]


def heal_schema(expected_cols: list[str], actual_cols: list[str]) -> dict[str, str]:
    """Ask a local LLM to map actual columns to the expected schema by meaning.

    Returns a {actual_column: expected_column} mapping.
    """
    prompt = (
        "You are a data engineering system. Map the actual data columns to the "
        "expected schema based on semantic meaning.\n"
        f"Expected columns: {expected_cols}\n"
        f"Actual columns: {actual_cols}\n"
        "Return ONLY a valid JSON object where keys are actual columns and values "
        "are expected columns. No markdown, no explanation."
    )
    response = requests.post(
        OLLAMA_URL,
        json={"model": MODEL, "prompt": prompt, "stream": False, "format": "json"},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return json.loads(response.json().get("response", "{}"))


def alert(message: str) -> None:
    """Hook for PagerDuty / email / Slack. Logs to stderr for now."""
    print(f"[ALERT] {message}", file=sys.stderr)


def process_data(df: pd.DataFrame, expected_schema: list[str]) -> pd.DataFrame:
    """Validate columns; heal via the LLM only when they drift."""
    actual_cols = list(df.columns)

    if set(actual_cols) == set(expected_schema):
        print("Schema validation passed.")
        return df[expected_schema]

    print("WARNING: schema mismatch detected. Initiating self-healing...")
    mapping = heal_schema(expected_schema, actual_cols)
    if not mapping:
        alert("Self-healing returned no mapping.")
        raise RuntimeError("Self-healing failed to return a valid mapping.")

    # Guard against a non-bijective mapping: two source columns mapping to the
    # same target would collide on rename and silently drop data.
    targets = list(mapping.values())
    if len(set(targets)) != len(targets):
        alert(f"Non-bijective mapping rejected (duplicate targets): {mapping}")
        raise ValueError(f"Self-healing produced a non-bijective mapping: {mapping}")

    df = df.rename(columns=mapping)
    missing = [col for col in expected_schema if col not in df.columns]
    if missing:
        alert(f"Unrecoverable schema drift. Still missing: {missing}")
        raise KeyError(f"Schema healing incomplete: {missing}")

    print(f"Healing successful. Applied mapping: {mapping}")
    return df[expected_schema]


def _demo() -> None:
    incoming = pd.DataFrame(
        {
            "txn_id": ["A1", "A2"],
            "email_address": ["alice@test.com", "bob@test.com"],
            "total_cost": [150.00, 89.50],
            "date": ["2026-05-26", "2026-05-26"],
        }
    )
    healed = process_data(incoming, EXPECTED_SCHEMA)
    print("\nFinal DataFrame:")
    print(healed.head())


if __name__ == "__main__":
    _demo()
