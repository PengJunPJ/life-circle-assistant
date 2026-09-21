from __future__ import annotations

from typing import Any


SOURCE_LABELS = {
    "real_api": "真实 API",
    "cache": "有效缓存",
    "local_snapshot": "本地快照",
    "interpolation": "空间插值",
    "degraded_estimate": "降级估算",
}


def source_label(source: Any, *, fallback: str = "未提供") -> str:
    """返回报告、导出共用的数据来源中文标签。"""
    normalized = str(source) if source is not None and str(source) else fallback
    return SOURCE_LABELS.get(normalized, normalized)
