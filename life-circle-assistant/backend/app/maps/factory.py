from __future__ import annotations

from ..baidu import BaiduMapClient
from ..local_snapshot import load_snapshot
from .baidu import BaiduMapProvider
from .provider import MapProvider
from .snapshot import SnapshotMapProvider


def create_map_provider() -> MapProvider:
    client = BaiduMapClient()
    if client.real_available:
        return BaiduMapProvider(client)
    return SnapshotMapProvider(load_snapshot())
