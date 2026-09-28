from __future__ import annotations

# V2 只交付广州市黄埔区样例。边界采用覆盖黄埔区的保守矩形，避免把其他城市或城区
# 的地址误当成本版本可分析范围；精确行政区判断可在后续接入行政区划数据后替换。
HUANGPU_BOUNDS = {
    "min_lng": 113.35,
    "max_lng": 113.65,
    "min_lat": 22.95,
    "max_lat": 23.40,
}


def is_in_supported_huangpu_area(lng: float, lat: float) -> bool:
    return (
        HUANGPU_BOUNDS["min_lng"] <= lng <= HUANGPU_BOUNDS["max_lng"]
        and HUANGPU_BOUNDS["min_lat"] <= lat <= HUANGPU_BOUNDS["max_lat"]
    )


def require_supported_huangpu_area(lng: float, lat: float) -> None:
    if not is_in_supported_huangpu_area(lng, lat):
        raise ValueError("该位置超出当前支持范围；V2 仅支持广州市黄埔区样例")
