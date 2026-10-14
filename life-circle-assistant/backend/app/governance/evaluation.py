"""Independent labeled semantic evaluation: uncertainty is not a correct merge."""

from __future__ import annotations

from ..analysis.semantic_review import review_facility_semantics
from ..mock_data import CATEGORIES


async def evaluate_semantics(dataset: dict, *, embedder=None, provider=None):
    communities = dataset.get("communities")
    if (
        not isinstance(communities, list)
        or not communities
        or not isinstance(dataset.get("label_source"), str)
        or not dataset["label_source"].strip()
    ):
        raise ValueError("评估需要独立标注来源和社区样本")
    ids = [item["community_id"] for item in communities]
    if any(not isinstance(identifier, str) or not identifier.strip() for identifier in ids) or len(set(ids)) != len(
        ids
    ):
        raise ValueError("社区标识重复")
    results = []
    for community in communities:
        records = community["records"]
        record_ids = {record["id"] for record in records}
        if len(record_ids) != len(records) or any(
            not isinstance(identifier, str) or not identifier.strip() for identifier in record_ids
        ):
            raise ValueError("评估记录标识无效或重复")
        labels = community.get("category_labels", {})
        if not labels or not set(labels) <= record_ids or not set(labels.values()) <= set(CATEGORIES):
            raise ValueError("分类人工标签缺失或引用未知记录")
        seen_pairs = set()
        for pair in community.get("entity_labels", []):
            key = frozenset((pair["left_id"], pair["right_id"]))
            if len(key) != 2 or not key <= record_ids or type(pair["same_entity"]) is not bool or key in seen_pairs:
                raise ValueError("实体人工标签无效或重复")
            seen_pairs.add(key)
        review = await review_facility_semantics(
            records, provider, embedder=embedder, coordinate_system=community.get("coordinate_system", "BD09")
        )
        predictions = {
            p["record_id"]: p.get("proposed_category")
            or (p["candidate_categories"][0] if len(p["candidate_categories"]) == 1 else None)
            for p in review["category_proposals"]
        }
        correct = sum(predictions[identifier] == label for identifier, label in labels.items())
        abstentions = sum(predictions[identifier] is None for identifier in labels)
        entity_predictions = {
            frozenset((p["left_id"], p["right_id"])): p["relation"] for p in review["entity_proposals"]
        }
        tp = fp = fn = tn = unresolved = negative_labels = 0
        for pair in community.get("entity_labels", []):
            key = frozenset((pair["left_id"], pair["right_id"]))
            prediction = entity_predictions.get(key, "not_recalled")
            positive = prediction == "same_entity"
            undecided = prediction in {"uncertain", "not_recalled"}
            unresolved += undecided
            negative_labels += not pair["same_entity"]
            tp += positive and pair["same_entity"]
            fp += positive and not pair["same_entity"]
            fn += not positive and pair["same_entity"]
            tn += not positive and not pair["same_entity"] and not undecided

        def ratio(numerator, denominator):
            return round(numerator / denominator, 4) if denominator else None

        results.append(
            {
                "community_id": community["community_id"],
                "category_accuracy": ratio(correct, len(labels)),
                "category_count": len(labels),
                "category_correct": correct,
                "category_abstentions": abstentions,
                "true_merges": tp,
                "false_merges": fp,
                "missed_merges": fn,
                "true_non_merges": tn,
                "false_merge_rate": ratio(fp, negative_labels),
                "missed_merge_rate": ratio(fn, tp + fn),
                "merge_precision": ratio(tp, tp + fp),
                "merge_recall": ratio(tp, tp + fn),
                "unresolved_pairs": unresolved,
                "review_mode": review["mode"],
            }
        )
    count = sum(item["category_count"] for item in results)
    return {
        "contract_version": "semantic-independent-evaluation-v1",
        "label_source": dataset["label_source"],
        "dataset_kind": dataset.get("dataset_kind", "unspecified"),
        "community_count": len(results),
        "community_isolation": True,
        "category_accuracy": round(sum(item["category_correct"] for item in results) / count, 4),
        "false_merges": sum(item["false_merges"] for item in results),
        "missed_merges": sum(item["missed_merges"] for item in results),
        "communities": results,
        "disclosure": "各社区候选分别生成，标签不传入模型；合成样本只能验证实现，不能证明现场效果。",
    }
