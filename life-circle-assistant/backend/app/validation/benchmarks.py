from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

VerifiedAreaKind = Literal["normal", "sparse", "critical"]
PredictedAreaKind = Literal["normal", "sparse", "critical", "unknown"]
BenchmarkStatus = Literal["draft", "verified"]

VERIFIED_KINDS: tuple[VerifiedAreaKind, ...] = ("normal", "sparse", "critical")
PREDICTED_KINDS: tuple[PredictedAreaKind, ...] = (*VERIFIED_KINDS, "unknown")
KIND_LABELS = {
    "normal": "正常覆盖区",
    "sparse": "设施稀疏区",
    "critical": "重点服务盲区",
    "unknown": "计算不完整",
}


class BenchmarkCommunity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    center_lng: float
    center_lat: float
    address: str = ""


class BenchmarkEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str = ""
    checked_at: str = ""
    reviewer: str = ""
    notes: str = ""


class BenchmarkLabel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grid_id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    expected_kind: VerifiedAreaKind | None = None
    evidence: BenchmarkEvidence = Field(default_factory=BenchmarkEvidence)


class CommunityBenchmark(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    benchmark_id: str = Field(min_length=1)
    status: BenchmarkStatus = "draft"
    community: BenchmarkCommunity
    coordinate_system: Literal["BD-09"] = "BD-09"
    threshold_minutes: int = Field(gt=0)
    grid_size: int = Field(gt=0)
    categories: list[str] = Field(min_length=1)
    labels: list[BenchmarkLabel] = Field(min_length=1)
    notes: str = ""

    @model_validator(mode="after")
    def validate_inventory(self) -> CommunityBenchmark:
        if len(self.categories) != len(set(self.categories)):
            raise ValueError("设施类别不得重复")

        grid_ids = [label.grid_id for label in self.labels]
        if len(grid_ids) != len(set(grid_ids)):
            raise ValueError("基准文件中存在重复网格编号")

        expected_grid_ids = {
            f"{category}-r{row}c{column}"
            for category in self.categories
            for row in range(1, self.grid_size + 1)
            for column in range(1, self.grid_size + 1)
        }
        actual_grid_ids = set(grid_ids)
        missing = sorted(expected_grid_ids - actual_grid_ids)
        extra = sorted(actual_grid_ids - expected_grid_ids)
        if missing or extra:
            details = []
            if missing:
                details.append(f"缺少 {len(missing)} 个网格：{', '.join(missing[:5])}")
            if extra:
                details.append(f"存在 {len(extra)} 个非法网格：{', '.join(extra[:5])}")
            raise ValueError("基准网格清单不完整；" + "；".join(details))

        for label in self.labels:
            expected_category, separator, _cell_id = label.grid_id.rpartition("-")
            if not separator or expected_category != label.category:
                raise ValueError(f"{label.grid_id} 与类别 {label.category} 不匹配")
            if label.category not in self.categories:
                raise ValueError(f"{label.grid_id} 使用了未声明的类别 {label.category}")

        unreviewed = [label.grid_id for label in self.labels if label.expected_kind is None]
        if self.status == "verified" and unreviewed:
            raise ValueError(f"已验证基准仍有 {len(unreviewed)} 个网格未标注")
        return self


def _service_area_features(report: dict[str, Any]) -> list[dict[str, Any]]:
    collection = report.get("service_areas") or report.get("zones")
    if not isinstance(collection, dict) or not isinstance(collection.get("features"), list):
        raise ValueError("体检报告缺少 service_areas/zones GeoJSON 数据")
    return collection["features"]


def _prediction_map(report: dict[str, Any]) -> dict[str, PredictedAreaKind]:
    predictions: dict[str, PredictedAreaKind] = {}
    for feature in _service_area_features(report):
        properties = feature.get("properties") if isinstance(feature, dict) else None
        if not isinstance(properties, dict):
            raise ValueError("服务区域要素缺少 properties")
        grid_id = properties.get("grid_id")
        kind = properties.get("kind")
        if not isinstance(grid_id, str) or not grid_id:
            raise ValueError("服务区域要素缺少 grid_id")
        if grid_id in predictions:
            raise ValueError(f"体检报告中存在重复网格 {grid_id}")
        if kind not in PREDICTED_KINDS:
            raise ValueError(f"{grid_id} 包含不支持的分类 {kind!r}")
        predictions[grid_id] = kind
    return predictions


def generate_benchmark_template(
    report: dict[str, Any],
    *,
    benchmark_id: str,
    community_name: str | None = None,
) -> dict[str, Any]:
    """从体检报告生成待人工标注的全网格模板。

    模板故意不写入系统预测类别，避免在人工核查时引入确证偏差。
    """
    predictions = _prediction_map(report)
    center = report.get("analysis_center") or report.get("center") or {}
    parameters = report.get("request") or report.get("parameters") or {}

    categories: list[str] = []
    labels: list[dict[str, Any]] = []
    row_column_indexes: list[tuple[int, int]] = []
    for grid_id in predictions:
        category, separator, cell_id = grid_id.rpartition("-")
        if not separator or not cell_id.startswith("r") or "c" not in cell_id:
            raise ValueError(f"无法从网格编号解析类别与行列：{grid_id}")
        row_text, column_text = cell_id[1:].split("c", 1)
        try:
            row_column_indexes.append((int(row_text), int(column_text)))
        except ValueError as exc:
            raise ValueError(f"网格编号行列不是整数：{grid_id}") from exc
        if category not in categories:
            categories.append(category)
        labels.append(
            {
                "grid_id": grid_id,
                "category": category,
                "expected_kind": None,
                "evidence": {"source": "", "checked_at": "", "reviewer": "", "notes": ""},
            }
        )

    grid_size = max(max(row, column) for row, column in row_column_indexes)
    labels.sort(key=lambda item: (categories.index(item["category"]), item["grid_id"]))
    template = CommunityBenchmark(
        benchmark_id=benchmark_id,
        status="draft",
        community=BenchmarkCommunity(
            name=community_name or center.get("address") or benchmark_id,
            center_lng=center.get("lng"),
            center_lat=center.get("lat"),
            address=center.get("address", ""),
        ),
        threshold_minutes=parameters.get("minutes", 15),
        grid_size=grid_size,
        categories=categories,
        labels=[BenchmarkLabel.model_validate(item) for item in labels],
        notes="请使用独立地图或现场证据逐格填写 expected_kind 和 evidence，完成后将 status 改为 verified。",
    )
    return template.model_dump(mode="json")


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def _average(values: list[float | None]) -> float | None:
    actual = [value for value in values if value is not None]
    return round(sum(actual) / len(actual), 4) if actual else None


def _metrics_from_matrix(matrix: dict[str, dict[str, int]]) -> dict[str, Any]:
    total = sum(sum(row.values()) for row in matrix.values())
    correct = sum(matrix[kind][kind] for kind in VERIFIED_KINDS)
    unknown = sum(matrix[kind]["unknown"] for kind in VERIFIED_KINDS)
    per_kind: dict[str, Any] = {}

    for kind in VERIFIED_KINDS:
        true_positive = matrix[kind][kind]
        false_positive = sum(matrix[actual][kind] for actual in VERIFIED_KINDS if actual != kind)
        false_negative = sum(matrix[kind][predicted] for predicted in PREDICTED_KINDS if predicted != kind)
        actual_support = true_positive + false_negative
        predicted_support = true_positive + false_positive
        precision = _safe_ratio(true_positive, predicted_support)
        if precision is None and actual_support:
            precision = 0.0
        recall = _safe_ratio(true_positive, actual_support)
        if not actual_support and not predicted_support:
            f1 = None
        elif precision is None or recall is None or precision + recall == 0:
            f1 = 0.0
        else:
            f1 = round(2 * precision * recall / (precision + recall), 4)
        per_kind[kind] = {
            "label": KIND_LABELS[kind],
            "support": sum(matrix[kind].values()),
            "true_positive": true_positive,
            "false_positive": false_positive,
            "false_negative": false_negative,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }

    return {
        "evaluated_count": total,
        "correct_count": correct,
        "unknown_prediction_count": unknown,
        "accuracy": _safe_ratio(correct, total),
        "prediction_coverage": _safe_ratio(total - unknown, total),
        "macro_precision": _average([per_kind[kind]["precision"] for kind in VERIFIED_KINDS]),
        "macro_recall": _average([per_kind[kind]["recall"] for kind in VERIFIED_KINDS]),
        "macro_f1": _average([per_kind[kind]["f1"] for kind in VERIFIED_KINDS]),
        "per_kind": per_kind,
    }


def _empty_matrix() -> dict[str, dict[str, int]]:
    return {actual: {predicted: 0 for predicted in PREDICTED_KINDS} for actual in VERIFIED_KINDS}


def evaluate_benchmark(report: dict[str, Any], benchmark_data: dict[str, Any]) -> dict[str, Any]:
    benchmark = CommunityBenchmark.model_validate(benchmark_data)
    predictions = _prediction_map(report)
    benchmark_grid_ids = {label.grid_id for label in benchmark.labels}
    missing_prediction_grid_ids = sorted(benchmark_grid_ids - predictions.keys())
    extra_prediction_grid_ids = sorted(predictions.keys() - benchmark_grid_ids)

    overall_matrix = _empty_matrix()
    category_matrices = {category: _empty_matrix() for category in benchmark.categories}
    mismatches: list[dict[str, str]] = []
    reviewed_labels = [label for label in benchmark.labels if label.expected_kind is not None]

    for label in reviewed_labels:
        predicted = predictions.get(label.grid_id, "unknown")
        expected = label.expected_kind
        assert expected is not None
        overall_matrix[expected][predicted] += 1
        category_matrices[label.category][expected][predicted] += 1
        if predicted != expected:
            mismatches.append(
                {
                    "grid_id": label.grid_id,
                    "category": label.category,
                    "expected_kind": expected,
                    "predicted_kind": predicted,
                }
            )

    label_count = len(benchmark.labels)
    reviewed_count = len(reviewed_labels)
    result = {
        "schema_version": "1.0",
        "evaluated_at": datetime.now(UTC).isoformat(),
        "benchmark": {
            "benchmark_id": benchmark.benchmark_id,
            "status": benchmark.status,
            "community": benchmark.community.model_dump(mode="json"),
            "coordinate_system": benchmark.coordinate_system,
            "threshold_minutes": benchmark.threshold_minutes,
            "grid_size": benchmark.grid_size,
            "categories": benchmark.categories,
        },
        "completeness": {
            "expected_label_count": label_count,
            "reviewed_label_count": reviewed_count,
            "review_completion_rate": _safe_ratio(reviewed_count, label_count),
            "is_verified_full_grid": benchmark.status == "verified" and reviewed_count == label_count,
            "missing_prediction_grid_ids": missing_prediction_grid_ids,
            "extra_prediction_grid_ids": extra_prediction_grid_ids,
        },
        "confusion_matrix": overall_matrix,
        "metrics": _metrics_from_matrix(overall_matrix),
        "category_results": {
            category: {
                "confusion_matrix": category_matrices[category],
                "metrics": _metrics_from_matrix(category_matrices[category]),
            }
            for category in benchmark.categories
        },
        "mismatches": mismatches,
        "prediction_counts": dict(Counter(predictions.values())),
    }
    return result


def _format_metric(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def render_markdown_report(evaluation: dict[str, Any]) -> str:
    benchmark = evaluation["benchmark"]
    completeness = evaluation["completeness"]
    metrics = evaluation["metrics"]
    matrix = evaluation["confusion_matrix"]
    lines = [
        f"# {benchmark['community']['name']} 全网格基准评估",
        "",
        f"- 基准编号：`{benchmark['benchmark_id']}`",
        f"- 基准状态：`{benchmark['status']}`",
        f"- 分析坐标系：`{benchmark['coordinate_system']}`",
        f"- 步行阈值：{benchmark['threshold_minutes']} 分钟",
        f"- 标注完成度：{completeness['reviewed_label_count']} / {completeness['expected_label_count']}（{_format_metric(completeness['review_completion_rate'])}）",
        f"- 已验证全网格：{'yes' if completeness['is_verified_full_grid'] else 'no'}",
        "",
        "## 总体指标",
        "",
        "| 指标 | 结果 |",
        "| --- | ---: |",
        f"| 参与评估的网格 | {metrics['evaluated_count']} |",
        f"| 准确率 | {_format_metric(metrics['accuracy'])} |",
        f"| 有效预测覆盖率 | {_format_metric(metrics['prediction_coverage'])} |",
        f"| 宏平均精确率 | {_format_metric(metrics['macro_precision'])} |",
        f"| 宏平均召回率 | {_format_metric(metrics['macro_recall'])} |",
        f"| 宏平均 F1 | {_format_metric(metrics['macro_f1'])} |",
        f"| 计算不完整预测 | {metrics['unknown_prediction_count']} |",
        "",
        "## 混淆矩阵",
        "",
        "行为人工真值，列为系统预测。",
        "",
        "| 真值 \\ 预测 | 正常覆盖区 | 设施稀疏区 | 重点服务盲区 | 计算不完整 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for actual in VERIFIED_KINDS:
        row = matrix[actual]
        lines.append(
            f"| {KIND_LABELS[actual]} | {row['normal']} | {row['sparse']} | {row['critical']} | {row['unknown']} |"
        )

    lines.extend(
        [
            "",
            "## 分类别指标",
            "",
            "| 类别 | 样本数 | 准确率 | 有效预测覆盖率 | 宏平均 F1 |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for category in benchmark["categories"]:
        category_metrics = evaluation["category_results"][category]["metrics"]
        lines.append(
            f"| {category} | {category_metrics['evaluated_count']} | {_format_metric(category_metrics['accuracy'])} | "
            f"{_format_metric(category_metrics['prediction_coverage'])} | {_format_metric(category_metrics['macro_f1'])} |"
        )

    missing = completeness["missing_prediction_grid_ids"]
    extra = completeness["extra_prediction_grid_ids"]
    lines.extend(
        [
            "",
            "## 完整性与差异",
            "",
            f"- 报告缺失的基准网格：{len(missing)}",
            f"- 报告多出的网格：{len(extra)}",
            f"- 分类不一致网格：{len(evaluation['mismatches'])}",
        ]
    )
    if benchmark["status"] != "verified":
        lines.extend(["", "> 当前基准仍为草稿，指标只针对已标注网格，不得宣称为全网格准确率。"])
    return "\n".join(lines) + "\n"
