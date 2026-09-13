"""Tests for the legal engine. Run: ./.venv/bin/python -m pytest app/test_legal_engine.py -q"""
from datetime import date
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))

from legal_engine import assess, PRESCRIPTION_GOODS_DAYS


TODAY = date(2026, 9, 12)          # hackathon day, fixed for determinism


def test_ahmed_scenario_is_one_year_not_fifteen():
    """The demo scenario: 8000 TND, invoice 4 months old, carpenter."""
    a = assess(8000, '2026-05-12', 'menuiserie', today=TODAY)
    assert a.regime == 'goods_1y'
    assert a.deadline == '2027-05-12'
    assert a.days_left == 242
    assert not a.is_expired
    # the whole point: a naive model would answer 15 years
    assert a.days_left < 365


def test_expired_claim_is_flagged():
    a = assess(8000, '2024-01-10', 'menuiserie', today=TODAY)
    assert a.is_expired
    assert a.urgency == 'expired'
    assert a.days_left < 0


def test_service_activity_falls_under_general_regime():
    a = assess(8000, '2026-05-12', 'conseil', today=TODAY)
    assert a.regime == 'general_15y'
    assert a.deadline == '2041-05-12'


def test_bailiff_threshold_150_tnd():
    below = assess(120, '2026-05-12', 'menuiserie', today=TODAY)
    above = assess(151, '2026-05-12', 'menuiserie', today=TODAY)
    assert not below.needs_bailiff
    assert above.needs_bailiff
    assert above.grace_days == 5


def test_every_source_has_an_arabic_citation():
    a = assess(8000, '2026-05-12', 'menuiserie', today=TODAY)
    assert a.sources, 'assessment must cite its sources'
    for s in a.sources:
        assert s['citation_ar'].startswith('الفصل')
        assert s['article'] > 0
    for st in a.steps:
        assert st.citation_ar.startswith('الفصل')


def test_urgency_bands():
    assert assess(8000, '2025-10-01', 'menuiserie', today=TODAY).urgency == 'critical'
    assert assess(8000, '2026-08-01', 'menuiserie', today=TODAY).urgency == 'ok'


def test_deadline_is_exactly_365_days():
    a = assess(500, '2026-01-01', 'menuiserie', today=TODAY)
    assert (date.fromisoformat(a.deadline)
            - date(2026, 1, 1)).days == PRESCRIPTION_GOODS_DAYS
