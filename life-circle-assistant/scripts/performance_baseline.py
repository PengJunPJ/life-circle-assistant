#!/usr/bin/env python3
"""对运行中的后端执行可复现的快照/真实 API 性能采样。"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def request_json(base_url: str, path: str, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        data=body,
        method=method,
        headers={"Content-Type": "application/json"} if body else {},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def wait_for_report(base_url: str, task_id: str, timeout_seconds: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        task = request_json(base_url, f"/api/analyze/{task_id}")
        if task["status"] == "completed":
            return task["result"]
        if task["status"] == "failed":
            raise RuntimeError(task.get("error") or "分析失败")
        time.sleep(0.2)
    raise TimeoutError(f"等待任务 {task_id} 超过 {timeout_seconds:g} 秒")


def run_once(base_url: str, payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
    wall_started = time.perf_counter()
    task = request_json(base_url, "/api/analyze", "POST", payload)
    report = wait_for_report(base_url, task["id"], timeout_seconds)
    execution = report["execution"]
    return {
        "report_id": report["report_id"],
        "wall_duration_ms": round((time.perf_counter() - wall_started) * 1_000),
        "reported_duration_ms": execution["total_duration_ms"],
        "stage_durations_ms": execution.get("stage_durations_ms", {}),
        "api_calls": execution.get("api_calls", execution["metrics"].get("walking_api_calls", 0)),
        "cache": execution.get("cache", {}),
        "walking_provider_calls": execution["metrics"].get("walking_provider_calls", 0),
        "walking_failures": execution["metrics"].get("walking_failures", 0),
        "completeness": report["completeness"],
    }


def summarize(runs: list[dict[str, Any]]) -> dict[str, Any]:
    values = [item["wall_duration_ms"] for item in runs]
    return {
        "runs": runs,
        "summary": {
            "run_count": len(runs),
            "wall_duration_ms_median": round(statistics.median(values)),
            "wall_duration_ms_min": min(values),
            "wall_duration_ms_max": max(values),
            "total_api_calls": sum(item["api_calls"] for item in runs),
            "total_cache_hits": sum(item.get("cache", {}).get("hits", 0) for item in runs),
            "warm_run_api_reduction": runs[0]["api_calls"] - runs[-1]["api_calls"] if len(runs) > 1 else 0,
            "warm_run_duration_reduction_ms": runs[0]["reported_duration_ms"] - runs[-1]["reported_duration_ms"] if len(runs) > 1 else 0,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="采样生活圈分析性能并输出 JSON 基线")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--runs", type=int, default=2, help="至少运行两次才能观测缓存收益")
    parser.add_argument("--mode", choices=("demo", "analysis"), default="demo")
    parser.add_argument("--minutes", type=int, choices=(10, 15, 20), default=15)
    parser.add_argument("--categories", default="market,pharmacy,school,medical")
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs 必须至少为 1")

    health = request_json(args.base_url, "/api/health")
    payload = {
        "minutes": args.minutes,
        "mode": args.mode,
        "categories": [item.strip() for item in args.categories.split(",") if item.strip()],
    }
    result = {
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "base_url": args.base_url,
        "provider_mode": health.get("provider_mode"),
        "request": payload,
        **summarize([run_once(args.base_url, payload, args.timeout) for _ in range(args.runs)]),
    }
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    try:
        main()
    except urllib.error.URLError as exc:
        raise SystemExit(f"无法访问后端：{exc}") from exc
