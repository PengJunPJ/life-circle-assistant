"""对话只能操作声明式工作区状态，模型没有任意坐标/代码执行权限。"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .conversation_tools import STATUS_LAYERS
from .schemas import CenterSelectionMethod, CoreCategory


class WorkspaceCenter(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    lng: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)
    address: str = Field(default="", max_length=200)
    selection_method: CenterSelectionMethod = "default"


class WorkspaceState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    center: WorkspaceCenter | None = None
    minutes: Literal[10, 15, 20] = 15
    minutes_confirmed: bool = True
    mode: Literal["demo", "analysis"] = "analysis"
    categories: list[CoreCategory] = Field(
        default_factory=lambda: ["market", "pharmacy", "school", "medical"], max_length=7
    )
    report_id: str | None = Field(default=None, max_length=120)
    grid_id: str | None = Field(default=None, max_length=120)
    visible_categories: list[CoreCategory] = Field(
        default_factory=lambda: ["market", "pharmacy", "school", "medical"], max_length=7
    )
    analysis_task_id: str | None = Field(default=None, max_length=120)
    status_layers: dict[str, bool] = Field(default_factory=lambda: dict(STATUS_LAYERS))
    address_candidates: list[dict] = Field(default_factory=list, max_length=20)
    history_report_ids: list[str] = Field(default_factory=list, max_length=20)
    task_plan: list[dict] = Field(default_factory=list, max_length=6)
    clarification: dict | None = None

    @field_validator("status_layers")
    @classmethod
    def known_layers(cls, value):
        if not set(value) <= set(STATUS_LAYERS):
            raise ValueError("不支持的地图状态图层")
        return {**STATUS_LAYERS, **value}

    @field_validator("categories", "visible_categories")
    @classmethod
    def unique_categories(cls, value):
        return list(dict.fromkeys(value))


class CreateWorkspace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: WorkspaceState = Field(default_factory=WorkspaceState)


class UpdateWorkspace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    state: WorkspaceState


class ConversationMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9_-]+$")
    expected_revision: int = Field(ge=0)
    message: str = Field(min_length=1, max_length=1000)
    confirm_token: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("message")
    @classmethod
    def trim_message(cls, value):
        if not value.strip():
            raise ValueError("请输入要操作或询问的内容")
        return value.strip()
