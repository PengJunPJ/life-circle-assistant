from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

CoreCategory = Literal[
    "market",
    "pharmacy",
    "school",
    "medical",
    "elderly",
    "park",
    "convenience",
]
CenterSelectionMethod = Literal["default", "address", "map", "coordinates"]
SimulationSelectionMethod = Literal["recommendation", "map"]
CoordinateSystem = Literal["wgs84", "gcj02", "bd09"]


class CoordinateConversionRequest(BaseModel):
    lng: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    from_system: CoordinateSystem


class AnalyzeRequest(BaseModel):
    """创建一次生活圈分析的外部输入。

    Pydantic 会先完成类型和范围校验；更复杂的业务规则（例如是否在黄埔区）
    放在地图支持范围模块中，避免把 HTTP 输入模型变成业务服务的容器。
    """

    lng: float = Field(default=113.4872, ge=-180, le=180)
    lat: float = Field(default=23.1068, ge=-90, le=90)
    minutes: Literal[10, 15, 20] = 15
    mode: Literal["demo", "analysis"] = "demo"
    categories: list[CoreCategory] = Field(
        default_factory=lambda: ["market", "pharmacy", "school", "medical"], min_length=1
    )
    center_address: str = Field(default="", max_length=200)
    center_selection_method: CenterSelectionMethod = "default"

    @field_validator("categories")
    @classmethod
    def deduplicate_categories(cls, categories: list[CoreCategory]) -> list[CoreCategory]:
        return list(dict.fromkeys(categories))


class AnalysisIntentDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    address: str = Field(default="", max_length=200)
    use_current_center: bool = False
    minutes: Literal[10, 15, 20] | None = 15
    mode: Literal["demo", "analysis"] = "demo"
    categories: list[CoreCategory] = Field(
        default_factory=lambda: ["market", "pharmacy", "school", "medical", "elderly", "park", "convenience"],
        max_length=7,
    )
    defaulted_fields: list[Literal["minutes", "mode", "categories"]] = Field(
        default_factory=lambda: ["minutes", "mode", "categories"], max_length=3
    )


class AnalysisIntentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=1000)
    previous: AnalysisIntentDraft | None = None

    @field_validator("message")
    @classmethod
    def require_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("请描述要体检的社区或补充参数")
        return value.strip()


class AnalysisIntentResponse(BaseModel):
    draft: AnalysisIntentDraft
    parser: Literal["llm", "rules", "rules_degraded"]
    model: str | None = None
    missing_fields: list[Literal["location", "minutes", "categories"]]
    message: str


class ReportComparisonRequest(BaseModel):
    report_ids: list[str] = Field(min_length=2, max_length=2)

    @field_validator("report_ids")
    @classmethod
    def require_distinct_reports(cls, report_ids: list[str]) -> list[str]:
        normalized = [report_id.strip() for report_id in report_ids]
        if any(not report_id for report_id in normalized):
            raise ValueError("报告标识不能为空")
        if len(set(normalized)) != 2:
            raise ValueError("请选择两份不同的报告")
        return normalized


class SimulationRequest(BaseModel):
    category: CoreCategory
    lng: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    selection_method: SimulationSelectionMethod
    candidate_id: str | None = Field(default=None, max_length=120)


class PlanningLocation(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    lng: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)


class PlanningRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=1000)
    previous_turn_id: str | None = Field(default=None, max_length=120)
    selected_location: PlanningLocation | None = None
    grid_id: str | None = Field(default=None, max_length=120)

    comparison_goal: Literal["reduce_critical_zones", "increase_coverage", "improve_overall_score"] | None = None

    @field_validator("message")
    @classmethod
    def require_question(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("请描述想查询或模拟的问题")
        return value.strip()
