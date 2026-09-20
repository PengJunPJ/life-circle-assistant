from typing import Literal

from pydantic import BaseModel, Field, field_validator


CoreCategory = Literal["market", "pharmacy", "school", "medical"]
CenterSelectionMethod = Literal["default", "address", "map", "coordinates"]

class AnalyzeRequest(BaseModel):
    lng: float = Field(default=113.4872, ge=-180, le=180)
    lat: float = Field(default=23.1068, ge=-90, le=90)
    minutes: Literal[10, 15, 20] = 15
    mode: Literal["demo", "analysis"] = "demo"
    categories: list[CoreCategory] = Field(default_factory=lambda: ["market", "pharmacy", "school", "medical"], min_length=1)
    center_address: str = Field(default="", max_length=200)
    center_selection_method: CenterSelectionMethod = "default"

    @field_validator("categories")
    @classmethod
    def deduplicate_categories(cls, categories: list[CoreCategory]) -> list[CoreCategory]:
        return list(dict.fromkeys(categories))


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
