from __future__ import annotations

from typing import Any

from ..analysis.facility_reconciliation import decide_candidate_features, reconcile_facilities

LABELS = {"match", "non_match", "conflict"}
PREDICTIONS = {"match", "non_match", "conflict", "needs_review"}


def evaluate_labeled_pairs(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    """Evaluate candidate-pair decisions against independent human labels.

    Raw records are consumed in memory and intentionally excluded from the returned
    audit result. Each pair should contain ``pair_id``, ``left``, ``right`` and a
    human ``label`` in ``match``/``non_match``/``conflict``.
    """
    matrix = {label: {prediction: 0 for prediction in sorted(PREDICTIONS)} for label in sorted(LABELS)}
    decisions: list[dict[str, Any]] = []
    true_positive = false_positive = false_negative = 0
    conflict_true_positive = conflict_total = needs_review_count = 0

    for pair in pairs:
        label = str(pair.get("label") or "")
        if label not in LABELS:
            raise ValueError(f"未知人工标签：{label!r}；允许值为 {sorted(LABELS)}")
        features = pair.get("features")
        if isinstance(features, dict):
            pair_decision = decide_candidate_features(**features)
        else:
            left = pair.get("left")
            right = pair.get("right")
            if not isinstance(left, dict) or not isinstance(right, dict):
                raise ValueError(f"样本 {pair.get('pair_id', '<unknown>')} 必须包含 features 或 left/right 记录")
            result = reconcile_facilities([left, right])
            pair_decision = next(iter(result.decisions), {})
        raw_decision = str(pair_decision.get("decision") or "unmatched")
        prediction = {
            "matched": "match",
            "unmatched": "non_match",
            "category_conflict": "conflict",
            "coordinate_system_conflict": "conflict",
            "needs_review": "needs_review",
        }.get(raw_decision, "non_match")
        matrix[label][prediction] += 1

        if prediction == "match" and label == "match":
            true_positive += 1
        elif prediction == "match":
            false_positive += 1
        elif label == "match":
            false_negative += 1
        if label == "conflict":
            conflict_total += 1
            conflict_true_positive += prediction == "conflict"
        needs_review_count += prediction == "needs_review"
        decisions.append(
            {
                "pair_id": str(pair.get("pair_id") or f"pair-{len(decisions) + 1}"),
                "human_label": label,
                "prediction": prediction,
                "match_score": pair_decision.get("match_score"),
                "distance_m": pair_decision.get("distance_m"),
                "category_match": pair_decision.get("category_match"),
            }
        )

    precision = _ratio(true_positive, true_positive + false_positive)
    recall = _ratio(true_positive, true_positive + false_negative)
    f1 = _ratio(2 * precision * recall, precision + recall)
    count = len(pairs)
    return {
        "rules_version": "1.0",
        "sample_count": count,
        "match_metrics": {"precision": precision, "recall": recall, "f1": f1},
        "human_conflict_recall": _ratio(conflict_true_positive, conflict_total),
        "conflict_rate": _ratio(sum(row["conflict"] for row in matrix.values()), count),
        "unresolved_rate": _ratio(needs_review_count, count),
        "confusion_matrix": matrix,
        "decisions": decisions,
    }


def _ratio(numerator: int | float, denominator: int | float) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0
