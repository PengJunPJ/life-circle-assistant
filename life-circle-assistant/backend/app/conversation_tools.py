"""统一声明式工具目录、受约束多步骤计划和对话上下文指代。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .planning_portfolio import compile_constraints
from .schemas import CoreCategory

STATUS_LAYERS = {
    "normal": True,
    "sparse": True,
    "critical": True,
    "unknown": True,
    "scarcity": False,
    "walking_timeout": False,
    "gap_groups": False,
    "sampling": False,
}


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal[
        "parameters",
        "analyze",
        "interpret",
        "plan",
        "history",
        "open_report",
        "layers",
        "focus",
        "export",
        "help",
        "semantic_review",
        "sampling",
        "coverage",
        "cancel",
        "retry",
        "status",
        "address_choice",
        "role_report",
        "feedback",
        "continue",
        "governance_status",
        "semantic_decision",
        "catalog_recompute",
        "observation_decision",
    ]
    categories: list[CoreCategory] | None = None
    grid_id: str | None = None
    export_format: Literal["json", "csv", "geojson", "geojson-wgs84", "pdf"] = "pdf"
    max_facilities: int = Field(default=2, ge=0, le=32)
    index: int = Field(default=1, ge=1, le=20)
    direction: str | None = None
    status_layers: dict[str, bool] | None = None
    constraints: dict | None = None
    audience: Literal["resident", "community", "planner"] = "resident"
    question: str | None = None
    decision: Literal["accept", "reject", "correct"] | None = None
    proposal_kind: Literal["category", "entity"] = "category"
    governance_payload: dict | None = None


@dataclass(frozen=True)
class ToolSpec:
    label: str
    requires_report: bool = False
    confirmation: bool = False
    route_pairs: int = 0
    model_calls: int = 0


TOOLS = {
    "parameters": ToolSpec("整理位置和分析参数", route_pairs=0, model_calls=2),
    "analyze": ToolSpec("按当前参数开始体检", confirmation=True, route_pairs=5000),
    "interpret": ToolSpec("从报告事实解答", requires_report=True, model_calls=1),
    "plan": ToolSpec("规划工具查询和复算", True, True, 256, 7),
    "history": ToolSpec("读取历史报告"),
    "open_report": ToolSpec("打开历史报告"),
    "layers": ToolSpec("调整共享地图图层"),
    "focus": ToolSpec("定位报告网格", True),
    "export": ToolSpec("导出报告", True, True),
    "help": ToolSpec("查看工具帮助"),
    "semantic_review": ToolSpec("生成设施语义审核", True, True, 0, 1),
    "sampling": ToolSpec("主动测量和预测图层", True, True, 40),
    "coverage": ToolSpec("硬约束组合选址及整体重算", True, True, 5000),
    "cancel": ToolSpec("取消正在运行的体检"),
    "retry": ToolSpec("从检查点恢复或重试体检", confirmation=True, route_pairs=5000),
    "status": ToolSpec("查询任务进度"),
    "address_choice": ToolSpec("选择已检索地址候选"),
    "role_report": ToolSpec("检索规范并按角色解释报告", True),
    "feedback": ToolSpec("提交待核验居民观察", True),
    "continue": ToolSpec("继续已经保存的任务计划"),
    "governance_status": ToolSpec("读取审核目录及居民观察", True),
    "semantic_decision": ToolSpec("确认设施语义审核决策", True, True),
    "catalog_recompute": ToolSpec("使用审核目录重新正式体检", True, True, 5000),
    "observation_decision": ToolSpec("确认居民观察审核决策", True, True),
}


def tool_manifest():
    from .planning_assistant import TOOL_REGISTRY

    return {
        "version": "workspace-tools-v3",
        "command_schema": Command.model_json_schema(),
        "tools": [{"name": name, **vars(spec)} for name, spec in TOOLS.items()],
        "planning_tools": [
            {"name": name, "label": value[1], "schema": value[0].model_json_schema()}
            for name, value in TOOL_REGISTRY.items()
        ],
        "policy": "模型只选择已注册受限工具；事实、地理和硬约束由确定性模块计算。",
    }


def split_workflow(message):
    # 硬约束中的分号是同一任务的数据分隔符，不能拆成独立操作而丢失约束。
    steps = [s.strip(" ，,；;") for s in re.split(r"然后|接着|随后", message) if s.strip(" ，,；;")]
    if len(steps) > 6:
        raise ValueError("一次任务计划最多六步，请分批执行")
    return steps


def ordinal(message):
    match = re.search(r"第\s*([0-9]+|[一二两三四五六七八九十])", message)
    if not match:
        return 1
    mapping = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    return int(match[1]) if match[1].isascii() else mapping[match[1]]


def observation_fields(message, kind):
    """只读取用户明示的核验字段；不会从观察文本或OCR推断设施身份。"""
    from .analysis_intent import CATEGORY_WORDS

    fields = {"kind": kind}
    facility = re.search(r"设施(?:ID|id|编号|标识)\s*[:：]?\s*([A-Za-z0-9_:-]+)", message)
    if facility:
        fields["facility_id"] = facility[1]
    for label, key in (("经度", "lng"), ("纬度", "lat")):
        match = re.search(label + r"\s*[:：]?\s*(-?\d+(?:\.\d+)?)", message)
        if match:
            fields[key] = float(match[1])
    for label, key in ((r"网格(?:1|一)", "first_grid_id"), (r"网格(?:2|二)", "second_grid_id")):
        match = re.search(label + r"\s*[:：]?\s*([A-Za-z0-9_:-]+)", message)
        if match:
            fields[key] = match[1]
    name = re.search(r"名称\s*[:：]\s*([^，,；;。]+)", message)
    if name:
        fields["name"] = name[1].strip()
    categories = [k for k, words in CATEGORY_WORDS.items() if any(w in message for w in words)]
    if len(categories) == 1:
        fields["category"] = categories[0]
    return fields


def quick_command(message, state):
    if re.search(r"重算|重新体检", message) and re.search(r"审核目录|设施目录|复核目录", message):
        return Command(kind="catalog_recompute")
    if re.search(r"查看|列出|查询", message) and re.search(r"居民观察|居民反馈|审核目录|审核记录", message):
        return Command(kind="governance_status")
    if re.search(r"接受|接纳|驳回|拒绝|修正", message) and re.search(
        r"分类建议|类别建议|实体建议|居民观察|居民反馈", message
    ):
        decision = "reject" if re.search(r"驳回|拒绝", message) else "correct" if "修正" in message else "accept"
        if re.search(r"居民观察|居民反馈", message):
            return Command(kind="observation_decision", index=ordinal(message), decision=decision, question=message)
        from .analysis_intent import CATEGORY_WORDS

        categories = [k for k, words in CATEGORY_WORDS.items() if any(w in message for w in words)]
        return Command(
            kind="semantic_decision",
            index=ordinal(message),
            decision=decision,
            proposal_kind="entity" if "实体建议" in message else "category",
            categories=categories or None,
            question=message,
        )
    if re.search(r"居民.*报告|社区(?:人员|工作人员).*报告|规划师.*报告", message):
        audience = "planner" if "规划师" in message else "community" if "社区" in message else "resident"
        return Command(kind="role_report", audience=audience)
    if re.search(r"取消|停止|终止", message) and re.search(r"体检|分析|任务", message):
        return Command(kind="cancel")
    if re.search(r"重试|续算|恢复.*任务", message):
        return Command(kind="retry")
    if re.search(r"进度|分析到哪|还要多久|任务状态", message):
        return Command(kind="status")
    if re.search(r"(?:打开|查看|切换到).*?(?:报告|历史)", message):
        return Command(kind="open_report", index=ordinal(message))
    if re.search(
        r"(?:选择|选|用|就是).*?第\s*(?:[0-9]+|[一二两三四五六七八九十]).*?(?:地址|位置|候选|个|项)|^第[一二两三四五六七八九十0-9]+(?:个|项)$",
        message,
    ):
        return Command(kind="address_choice", index=ordinal(message))
    if re.search(r"反馈|居民留言|围挡|疑似关闭|入口变更", message):
        return Command(kind="feedback", question=message)
    if re.fullmatch(r"继续|下一步|继续执行|继续计划", message):
        return Command(kind="continue")
    if re.search(r"图层|只看|显示|隐藏", message):
        aliases = {
            "scarcity": ["稀缺", "1公里", "一公里"],
            "walking_timeout": ["超时", "步行超时"],
            "critical": ["重点盲区", "重点缺口"],
            "gap_groups": ["缺口片区", "缺口分组"],
            "sampling": ["预测", "未决", "估计边界"],
        }
        selected = [key for key, words in aliases.items() if any(w in message for w in words)]
        if selected:
            layers = dict(state.get("status_layers") or STATUS_LAYERS)
            if "只看" in message:
                layers = {key: False for key in STATUS_LAYERS}
            for key in selected:
                layers[key] = "隐藏" not in message
            return Command(kind="layers", status_layers=layers)
    if re.search(r"定位|聚焦|选中", message):
        direction = next(
            (d for d in ("东北", "东南", "西北", "西南", "最东", "最西", "最北", "最南") if d in message), None
        )
        if direction:
            return Command(kind="focus", direction=direction)
    return None


def coverage_command(message, previous=None):
    constraints = compile_constraints(message, previous)
    from .analysis_intent import CATEGORY_WORDS

    categories = [k for k, words in CATEGORY_WORDS.items() if any(w in message for w in words)]
    return Command(
        kind="coverage",
        categories=categories or None,
        max_facilities=constraints.max_facilities,
        constraints=constraints.model_dump(),
    )


def resolve_grid(report, command):
    features = report.get("service_areas", {}).get("features", [])
    grids = {f["properties"].get("grid_id") for f in features}
    if command.grid_id in grids:
        return command.grid_id
    if not command.direction:
        raise ValueError("请提供当前报告中的网格标识，或直接点击地图网格")
    unique = {f["properties"]["grid_id"]: f for f in features}
    if not unique:
        raise ValueError("报告没有可定位网格")

    def rank(item):
        coordinates = item[1]["geometry"]["coordinates"][0]
        lng = sum(p[0] for p in coordinates) / len(coordinates)
        lat = sum(p[1] for p in coordinates) / len(coordinates)
        # 方向比较以网格行列为主，避免经纬度量纲决定角落。
        props = item[1]["properties"]
        east = props.get("grid_col", props.get("column", lng))
        north = -props["grid_row"] if "grid_row" in props else props.get("row", lat)
        directions = {
            "东北": (north, east),
            "东南": (-north, east),
            "西北": (north, -east),
            "西南": (-north, -east),
            "最东": (east, north),
            "最西": (-east, north),
            "最北": (north, east),
            "最南": (-north, east),
        }
        return (*directions[command.direction], item[0])

    return max(unique.items(), key=rank)[0]
