"""Tests for the healing logic (LLM call is monkeypatched — no network needed)."""

import pandas as pd
import pytest

import pipeline
from pipeline import EXPECTED_SCHEMA, process_data


def test_matching_schema_skips_llm(monkeypatch):
    def fail(*_args, **_kwargs):
        raise AssertionError("heal_schema must not be called when columns match")

    monkeypatch.setattr(pipeline, "heal_schema", fail)
    df = pd.DataFrame({c: [1] for c in EXPECTED_SCHEMA})
    out = process_data(df, EXPECTED_SCHEMA)
    assert list(out.columns) == EXPECTED_SCHEMA


def test_drift_is_healed(monkeypatch):
    mapping = {
        "txn_id": "transaction_id",
        "email_address": "customer_email",
        "total_cost": "purchase_amount",
        "date": "purchase_date",
    }
    monkeypatch.setattr(pipeline, "heal_schema", lambda *_: mapping)
    df = pd.DataFrame({k: ["x"] for k in mapping})
    out = process_data(df, EXPECTED_SCHEMA)
    assert list(out.columns) == EXPECTED_SCHEMA


def test_incomplete_healing_raises(monkeypatch):
    monkeypatch.setattr(pipeline, "heal_schema", lambda *_: {"txn_id": "transaction_id"})
    df = pd.DataFrame({"txn_id": ["x"], "junk": ["y"]})
    with pytest.raises(KeyError):
        process_data(df, EXPECTED_SCHEMA)
