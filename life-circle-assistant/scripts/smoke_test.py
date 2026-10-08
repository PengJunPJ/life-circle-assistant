import json
import os
import time
import urllib.error
import urllib.request


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
        task = request_json(f"http://localhost:8000/api/analyze/{task_id}")
        if task["status"] == "completed":
            return request_json(f"http://localhost:8000/api/report/{task_id}")
        if task["status"] == "failed":
            raise RuntimeError(task.get("error") or "体检任务失败")
        time.sleep(0.2)
    raise TimeoutError(f"等待演示模式体检报告超过 {timeout_seconds:g} 秒")


def main() -> None:
    health = request_json("http://localhost:8000/api/health")
    if health.get("status") != "ok" or health.get("mode") != "mock":
        raise RuntimeError(f"后端未以本地快照模式运行：{health}")

    task = request_json(
        "http://localhost:8000/api/analyze",
        method="POST",
        payload={"minutes": 15, "mode": "demo"},
    )
    report = wait_for_report(task["id"])
    if report.get("source") != "local_snapshot":
        raise RuntimeError(f"冒烟报告未使用本地快照：{report.get('source')}")
    if report.get("isochrone", {}).get("geometry", {}).get("type") != "Polygon":
        raise RuntimeError("冒烟报告缺少有效等时圈")
    pdf, content_type = request_bytes(
        f"http://localhost:8000/api/reports/{report['report_id']}/exports/pdf"
    )
    if content_type != "application/pdf" or not pdf.startswith(b"%PDF-"):
        raise RuntimeError("容器无法从持久化报告生成有效 PDF")

    with urllib.request.urlopen("http://localhost:5173", timeout=5) as response:
        page = response.read().decode("utf-8")
    if response.status != 200 or '<div id="app"></div>' not in page:
        raise RuntimeError("前端容器未返回应用入口页面")

    proxied_health = request_json("http://localhost:5173/api/health")
    if proxied_health.get("status") != "ok" or proxied_health.get("mode") != "mock":
        raise RuntimeError(f"前端 Nginx 未正确同源代理后端 API：{proxied_health}")

    print("容器冒烟验证通过：Nginx 静态前端与同源 API 可访问，后端健康，演示模式报告可生成 PDF。")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.URLError as exc:
        raise SystemExit(f"容器冒烟验证无法访问服务：{exc}") from exc
