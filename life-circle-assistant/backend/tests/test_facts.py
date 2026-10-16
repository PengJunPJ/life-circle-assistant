from copy import deepcopy

import pytest

from app.contracts.facts import FactValidationError, build_fact_catalog, claim_reference


def test_unknown_values_remain_unknown_and_catalog_owns_its_snapshot():
    report = {
        "report_id": "r",
        "summary": {"score": None, "critical_zone_count": 0},
        "facilities": [{"id": "f", "name": "药店", "walk_minutes": None}],
    }
    catalog = build_fact_catalog(report)
    report["summary"]["score"] = 99
    facts = catalog.validate_claims(
        [
            {"report_id": "r", "type": "report", "id": "r", "slot": "score"},
            {"report_id": "r", "type": "facility", "id": "f", "slot": "walk_minutes"},
            {"report_id": "r", "type": "report", "id": "r", "slot": "critical_zone_count"},
        ]
    )
    assert facts[0]["value"] is None and facts[0]["status"] == "unknown"
    assert "暂不可用" in facts[1]["text"]
    assert facts[2]["value"] == 0 and facts[2]["status"] == "available"
    assert "99" not in str(facts)
    facts[0]["evidence_refs"][0]["detail"] = "篡改值"
    assert "篡改值" not in str(catalog.allowed_claims())


@pytest.mark.parametrize(
    "change",
    [
        {"report_id": "foreign"},
        {"id": "unknown"},
        {"slot": "nearest_walk_minutes"},
        {"type": "facility"},
        {"value": 99},
        {"text": "总分99"},
        {"slot": 1},
    ],
)
def test_claim_requires_current_report_entity_and_exact_slot(change):
    catalog = build_fact_catalog({"report_id": "r", "summary": {"score": 68}})
    ref = {"report_id": "r", "type": "report", "id": "r", "slot": "score", **change}
    with pytest.raises(FactValidationError):
        catalog.validate_claims([ref])


def test_claim_request_round_trip_deduplicates_and_rejects_unbounded_lists():
    report = {"report_id": "r", "summary": {"score": 68}}
    original = deepcopy(report)
    catalog = build_fact_catalog(report)
    reference = claim_reference(catalog.allowed_claims()[0])
    assert len(catalog.validate_claims([reference, reference])) == 1
    with pytest.raises(FactValidationError):
        catalog.validate_claims([reference] * 21)
    with pytest.raises(FactValidationError):
        catalog.validate_claims({"claim": reference})
    assert report == original
