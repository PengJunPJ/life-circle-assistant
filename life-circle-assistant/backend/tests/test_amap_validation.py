import pytest

from app.amap import AmapPoi
from app.validation.amap_facility import AmapFacilityValidator


class FixtureAmapClient:
    configured = True

    def __init__(self, *, fail: bool = False):
        self.fail = fail

    async def convert_from_baidu(self, coordinates):
        return [(113.4808, 23.1015) for _ in coordinates]

    async def search_around(self, *, location_gcj02, keyword, radius_m):
        if self.fail:
            from app.amap import AmapError

            raise AmapError("测试限流", code="10021")
        return (
            [
                AmapPoi(
                    source_record_id="amap-1",
                    name="红山菜市场",
                    category="market",
                    lng=113.4809,
                    lat=23.1016,
                    address="测试路1号",
                )
            ],
            {"keyword": keyword, "pages": 1, "truncated": False, "returned_count": 1},
        )


class FixtureBaiduClient:
    real_available = True

    async def convert_coordinates(self, coordinates, model):
        assert model == 1
        return [{"lng": 113.48721, "lat": 23.10681} for _ in coordinates]


class FailingBaiduClient(FixtureBaiduClient):
    async def convert_coordinates(self, coordinates, model):
        from app.baidu import BaiduMapError

        raise BaiduMapError("测试坐标转换失败", code="fixture_conversion_failed")


def baidu_facility():
    return {
        "id": "baidu-1",
        "name": "红山菜市场",
        "canonical_name": "红山菜市场",
        "category": "market",
        "lng": 113.4872,
        "lat": 23.1068,
        "address": "测试路1号",
    }


@pytest.mark.asyncio
async def test_amap_validation_is_auxiliary_and_does_not_return_raw_pois():
    validator = AmapFacilityValidator(FixtureAmapClient(), FixtureBaiduClient())

    result = await validator.validate(
        [baidu_facility()], center_bd09=(113.4872, 23.1068), categories=["market"], radius_m=3000
    )

    assert result["status"] == "complete"
    assert result["affects_primary_analysis"] is False
    assert result["matched_count"] == 1
    assert result["returned_count"] == 3
    assert "facilities" not in result
    assert "name" not in result
    assert "address" not in result


@pytest.mark.asyncio
async def test_amap_failure_only_marks_auxiliary_validation_failed():
    validator = AmapFacilityValidator(FixtureAmapClient(fail=True), FixtureBaiduClient())

    result = await validator.validate(
        [baidu_facility()], center_bd09=(113.4872, 23.1068), categories=["market"], radius_m=3000
    )

    assert result["status"] == "failed"
    assert result["error_code"] == "10021"
    assert result["affects_primary_analysis"] is False


@pytest.mark.asyncio
async def test_coordinate_conversion_failure_is_contained_in_auxiliary_summary():
    validator = AmapFacilityValidator(FixtureAmapClient(), FailingBaiduClient())

    result = await validator.validate(
        [baidu_facility()], center_bd09=(113.4872, 23.1068), categories=["market"], radius_m=3000
    )

    assert result["status"] == "failed"
    assert result["error_code"] == "fixture_conversion_failed"
    assert result["affects_primary_analysis"] is False
