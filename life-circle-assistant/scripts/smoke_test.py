import argparse
import json
import os
import time
import urllib.error
import urllib.request

API_BASE_URL = os.getenv("SMOKE_API_URL", "http://localhost:8000")
WEB_BASE_URL = os.getenv("SMOKE_WEB_URL", "http://localhost:5173")


def request_json(url: str, method: str = "GET", payload: dict | None = None) -> dict:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={"Content-Type": "application/json"} if body else {},
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.load(response)


def request_bytes(url: str) -> tuple[bytes, str]:
    with urllib.request.urlopen(url, timeout=15) as response:
        return response.read(), response.headers.get_content_type()


def wait_for_report(task_id: str) -> dict:
    timeout_seconds = float(os.getenv("SMOKE_REPORT_TIMEOUT_SECONDS", "60"))
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        task = request_json(f"{API_BASE_URL}/api/analyze/{task_id}")
        if task["status"] == "completed":
            return request_json(f"{API_BASE_URL}/api/report/{task_id}")
        if task["status"] == "failed":
            raise RuntimeError(task.get("error") or "体检任务失败")
        time.sleep(0.2)
    raise TimeoutError(f"等待演示模式体检报告超过 {timeout_seconds:g} 秒")


def prepare_report(reuse_report: bool) -> dict:
    payload = {
        "minutes": 15,
        "mode": "demo",
        "categories": [
            "market",
            "pharmacy",
            "school",
            "medical",
            "elderly",
            "park",
            "convenience",
        ],
    }
    if reuse_report:
        # 只复用匹配演示参数的本地快照；翻页避免反复启动重复创建样例。
        offset = 0
        while True:
            history = request_json(
                f"{API_BASE_URL}/api/reports/history?limit=100&offset={offset}"
            )
            for item in history["items"]:
                report = request_json(f"{API_BASE_URL}/api/reports/{item['report_id']}")
                parameters = report["request"]
                if (
                    report.get("source") == "local_snapshot"
                    and all(
                        parameters.get(key) == value for key, value in payload.items()
                    )
                    and parameters.get("lng") == 113.53382359909054
                    and parameters.get("lat") == 23.08901171541019
                ):
                    print(f"复用已有示例报告：{report['report_id']}")
                    return report
            offset += len(history["items"])
            if not history["items"] or offset >= history["total"]:
                break
    task = request_json(f"{API_BASE_URL}/api/analyze", method="POST", payload=payload)
    report = wait_for_report(task["id"])
    print(f"已生成示例报告：{report['report_id']}")
    return report


def main(reuse_report: bool = False) -> None:
    health = request_json(f"{API_BASE_URL}/api/health")
    if health.get("status") != "ok" or health.get("mode") != "mock":
        raise RuntimeError(f"后端未以本地快照模式运行：{health}")

    report = prepare_report(reuse_report)
    if report.get("source") != "local_snapshot":
        raise RuntimeError(f"冒烟报告未使用本地快照：{report.get('source')}")
    if report.get("isochrone", {}).get("geometry", {}).get("type") != "Polygon":
        raise RuntimeError("冒烟报告缺少有效等时圈")
    exported = request_json(
        f"{API_BASE_URL}/api/reports/{report['report_id']}/exports/json"
    )
    # 用户可能已为复用的样例生成解读；导出允许附带这些记录。
    exported.pop("ai_interpretations", None)
    if exported != report:
        raise RuntimeError("JSON 导出与原始报告不一致")
    csv, csv_content_type = request_bytes(
        f"{API_BASE_URL}/api/reports/{report['report_id']}/exports/csv"
    )
    if csv_content_type != "text/csv" or not csv.strip():
        raise RuntimeError("容器未生成有效 CSV")
    pdf, content_type = request_bytes(
        f"{API_BASE_URL}/api/reports/{report['report_id']}/exports/pdf"
    )
    if content_type != "application/pdf" or not pdf.startswith(b"%PDF-"):
        raise RuntimeError("容器无法从持久化报告生成有效 PDF")

    standard = request_json(
        f"{API_BASE_URL}/api/reports/{report['report_id']}/exports/geojson-wgs84"
    )
    if (
        standard.get("coordinate_system") != "WGS84"
        or standard.get("source_coordinate_system") != "BD-09"
        or standard.get("parameters_coordinate_system") != "BD-09"
        or standard.get("parameters") != report["request"]
        or not standard.get("conversion_precision", {}).get("approximate")
    ):
        raise RuntimeError("容器标准 GeoJSON 未保留坐标来源、原始参数或近似说明")

    audience = request_json(
        f"{API_BASE_URL}/api/reports/{report['report_id']}/audience-report",
        method="POST",
        payload={"audience": "planner", "query": "评分和坐标规则"},
    )
    if (
        audience.get("audience") != "planner"
        or not audience.get("citations")
        or not audience.get("norms")
        or any(
            norm.get("scope") != "项目规则"
            or "/project_rules/" not in norm.get("source", "")
            for norm in audience["norms"]
        )
    ):
        raise RuntimeError("容器未打包项目规则或角色报告缺少可追溯引用")
    if request_json(f"{API_BASE_URL}/api/reports/{report['report_id']}") != report:
        raise RuntimeError("导出或角色报告修改了持久化来源报告")

    with urllib.request.urlopen(WEB_BASE_URL, timeout=5) as response:
        page = response.read().decode("utf-8")
    if response.status != 200 or '<div id="app"></div>' not in page:
        raise RuntimeError("前端容器未返回应用入口页面")

    proxied_health = request_json(f"{WEB_BASE_URL}/api/health")
    if proxied_health.get("status") != "ok" or proxied_health.get("mode") != "mock":
        raise RuntimeError(f"前端 Nginx 未正确同源代理后端 API：{proxied_health}")

    print(
        "容器冒烟验证通过：前后端健康、同源代理、JSON/CSV/PDF、标准WGS84导出及随包规范角色报告；原报告不变。"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="容器演示链路验证与示例报告准备")
    parser.add_argument(
        "--reuse-report", action="store_true", help="复用已有匹配样例，避免重复创建报告"
    )
    arguments = parser.parse_args()
    try:
        main(reuse_report=arguments.reuse_report)
    except urllib.error.URLError as exc:
        raise SystemExit(f"容器冒烟验证无法访问服务：{exc}") from exc
