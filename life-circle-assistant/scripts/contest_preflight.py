from __future__ import annotations

import argparse
import json
import re
import struct
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
SCREENSHOT_DIR = PROJECT_ROOT / "docs" / "contest" / "screenshots"
BRIEF_PATH = PROJECT_ROOT / "docs" / "contest" / "submission" / "15-minute-life-circle-competition-brief.pdf"
REPORT_DIR = PROJECT_ROOT / "docs" / "validation" / "reports" / "v2.3.0-20261012"
ROUTE_SCREENSHOT = SCREENSHOT_DIR / "07-walking-route.png"
DEMO_VIDEO = PROJECT_ROOT / "docs" / "contest" / "submission" / "v2.3.0-real-demo-20261012.webm"
EXPECTED_SCREENSHOTS = (
    "01-workspace-dark.png",
    "01-workspace-light.png",
    "02-isochrone-grid-dark.png",
    "02-isochrone-grid-light.png",
    "03-blindspot-evidence.png",
    "04-score-breakdown.png",
    "05-bar-tooltip.png",
    "06-radar-dark.png",
    "06-radar-light.png",
    "08-ai-interpretation.png",
    "09-simulation.png",
    "10-export-menu.png",
    "11-execution-metrics.png",
    "12-data-quality.png",
)


@dataclass(frozen=True)
class Check:
    id: str
    title: str
    status: str
    detail: str
    owner: str = "自动"


def run_git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=REPOSITORY_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as stream:
        header = stream.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("不是有效 PNG")
    return struct.unpack(">II", header[16:24])


def version_check() -> Check:
    expected = (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    package = json.loads((PROJECT_ROOT / "frontend" / "package.json").read_text(encoding="utf-8"))
    lockfile = json.loads((PROJECT_ROOT / "frontend" / "package-lock.json").read_text(encoding="utf-8"))
    backend = (PROJECT_ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    match = re.search(r'^APP_VERSION\s*=\s*["\']([^"\']+)["\']', backend, re.MULTILINE)
    versions = {
        "VERSION": expected,
        "package.json": package.get("version"),
        "package-lock.json": lockfile.get("version"),
        "package-lock 根包": lockfile.get("packages", {}).get("", {}).get("version"),
        "后端": match.group(1) if match else None,
    }
    mismatches = [f"{name}={value}" for name, value in versions.items() if value != expected]
    return Check(
        "version",
        "版本一致性",
        "pass" if not mismatches else "fail",
        f"全部为 {expected}" if not mismatches else "不一致：" + "，".join(mismatches),
    )


def governance_check() -> Check:
    required = (
        REPOSITORY_ROOT / "LICENSE",
        REPOSITORY_ROOT / "CONTRIBUTING.md",
        REPOSITORY_ROOT / "SECURITY.md",
        REPOSITORY_ROOT / "CODE_OF_CONDUCT.md",
        REPOSITORY_ROOT / "MAINTAINERS.md",
        PROJECT_ROOT / "docs" / "governance" / "open-source-governance.md",
        PROJECT_ROOT / "docs" / "contest" / "limitations.md",
        PROJECT_ROOT / "docs" / "contest" / "evidence-index.md",
    )
    missing = [str(path.relative_to(REPOSITORY_ROOT)) for path in required if not path.is_file()]
    return Check(
        "governance",
        "治理与披露文件",
        "pass" if not missing else "fail",
        "8 个必要文件齐全" if not missing else "缺少：" + "，".join(missing),
    )


def screenshot_check() -> Check:
    problems: list[str] = []
    for name in EXPECTED_SCREENSHOTS:
        path = SCREENSHOT_DIR / name
        if not path.is_file():
            problems.append(f"缺少 {name}")
            continue
        try:
            dimensions = png_dimensions(path)
        except ValueError as error:
            problems.append(f"{name}: {error}")
            continue
        if dimensions != (1600, 950):
            problems.append(f"{name}: {dimensions[0]}x{dimensions[1]}")
        if path.stat().st_size < 20_000:
            problems.append(f"{name}: 文件过小")
    return Check(
        "screenshots",
        "离线截图集",
        "pass" if not problems else "fail",
        f"{len(EXPECTED_SCREENSHOTS)} 张 1600x950 PNG 齐全" if not problems else "；".join(problems),
    )


def brief_check() -> Check:
    valid = BRIEF_PATH.is_file() and BRIEF_PATH.stat().st_size >= 100_000
    if valid:
        with BRIEF_PATH.open("rb") as stream:
            valid = stream.read(5) == b"%PDF-"
    detail = (
        f"{BRIEF_PATH.relative_to(PROJECT_ROOT)}（{BRIEF_PATH.stat().st_size // 1024} KiB）"
        if valid
        else "作品介绍 PDF 缺失、格式异常或小于 100 KiB"
    )
    return Check("brief", "作品介绍 PDF", "pass" if valid else "fail", detail)


def repository_check() -> list[Check]:
    remote = run_git("remote", "-v").stdout
    github_only = bool(remote.strip()) and all("github.com" in line for line in remote.splitlines())
    tracked = run_git("ls-files").stdout.splitlines()
    sensitive = [
        path
        for path in tracked
        if path.endswith((".db", ".sqlite", ".sqlite3", "-wal", "-shm"))
        or Path(path).name in {".env", ".env.local"}
    ]
    status = run_git("status", "--porcelain").stdout.splitlines()
    return [
        Check(
            "remote",
            "唯一远端仓库",
            "pass" if github_only else "fail",
            "所有已配置远端均指向 GitHub" if github_only else "存在非 GitHub 远端或未配置远端",
        ),
        Check(
            "secrets",
            "敏感运行文件未跟踪",
            "pass" if not sensitive else "fail",
            "未跟踪 .env、数据库或 WAL/SHM" if not sensitive else "发现：" + "，".join(sensitive),
        ),
        Check(
            "worktree",
            "提交工作树",
            "pass" if not status else "manual",
            "工作树干净" if not status else f"当前有 {len(status)} 条未提交变更；提交后复跑确认",
            "人工",
        ),
    ]


def manual_checks() -> list[Check]:
    reports = list(REPORT_DIR.glob("*.json")) if REPORT_DIR.is_dir() else []
    report_problems: list[str] = []
    valid_reports = 0
    for path in reports:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            report_problems.append(f"{path.name}: {error}")
            continue
        sources = payload.get("data_quality", {}).get("sources", [])
        has_real_baidu = payload.get("source") == "baidu" and any(
            item.get("kind") == "real_api" and item.get("provider") == "baidu-web-service"
            for item in sources
        )
        if not has_real_baidu:
            report_problems.append(f"{path.name}: 未发现百度真实 API 来源证据")
        if payload.get("completeness") != "complete":
            report_problems.append(f"{path.name}: completeness 不是 complete")
        else:
            valid_reports += 1
    report_detail = (
        f"{valid_reports} 份 v2.3.0 真实完整报告可解析"
        if valid_reports and not report_problems
        else "；".join(report_problems) or "未找到 v2.3.0 真实报告"
    )

    try:
        dimensions = png_dimensions(ROUTE_SCREENSHOT)
        route_ok = dimensions == (1600, 950) and ROUTE_SCREENSHOT.stat().st_size >= 20_000
    except (OSError, ValueError):
        route_ok = False
    route_detail = "真实路线截图存在且为 1600x950" if route_ok else "缺少或无法验证 07-walking-route.png"

    video_status = "manual"
    video_detail = "未生成明确命名的本地视频；公开链接仍需人工上传"
    if DEMO_VIDEO.is_file():
        duration = None
        try:
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(DEMO_VIDEO)],
                text=True,
                capture_output=True,
                check=False,
            )
            try:
                duration = float(probe.stdout.strip())
            except ValueError:
                pass
        except FileNotFoundError:
            video_detail = "本地视频已生成，但当前环境没有 ffprobe，无法自动确认时长；公开链接仍需人工上传"
            browser_probe = r'''const { chromium } = require("playwright-core");
(async () => {
  const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: true });
  try {
    const page = await browser.newPage();
    await page.goto("file://" + process.argv[1]);
    await page.waitForFunction(() => Number.isFinite(document.querySelector("video")?.duration), { timeout: 10000 });
    process.stdout.write(String(await page.evaluate(() => document.querySelector("video").duration)));
  } finally { await browser.close(); }
})().catch(() => process.exit(1));'''
            try:
                fallback = subprocess.run(
                    ["node", "-e", browser_probe, str(DEMO_VIDEO.resolve())],
                    cwd=PROJECT_ROOT / "frontend",
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=20,
                )
                if fallback.returncode == 0:
                    duration = float(fallback.stdout.strip())
            except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
                pass
        if duration is not None and 180 <= duration <= 300:
            video_status = "pass"
            video_detail = f"本地视频已生成（{duration:.1f} 秒）；公开链接仍需人工上传"
        else:
            video_detail = f"本地视频存在但时长未满足 3–5 分钟（{duration!s} 秒）；公开链接仍需人工上传"

    return [
        Check("real-report", "2.3.0 候选版真实百度报告", "pass" if valid_reports and not report_problems else "fail", report_detail),
        Check("walking-route", "真实步行路线截图", "pass" if route_ok else "fail", route_detail),
        Check("demo-video", "3–5 分钟演示视频", video_status, video_detail, "自动+人工"),
        Check("submission-receipt", "报名与提交回执", "manual", "需在赛事平台或邮件流程完成并保存回执", "人工"),
        Check("remote-ci-release", "远端门禁与正式发布", "manual", "候选提交合并 main 后重跑 CI，再创建 v2.3.0 标签与 Release", "人工"),
    ]


def collect_checks() -> list[Check]:
    return [
        version_check(),
        governance_check(),
        screenshot_check(),
        brief_check(),
        *repository_check(),
        *manual_checks(),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="检查参赛自动交付物，并单列必须人工完成的事项。")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    parser.add_argument("--strict", action="store_true", help="人工事项未完成时也返回非零退出码")
    args = parser.parse_args()
    checks = collect_checks()
    summary = {status: sum(item.status == status for item in checks) for status in ("pass", "fail", "manual")}

    if args.json:
        print(json.dumps({"checks": [asdict(item) for item in checks], "summary": summary}, ensure_ascii=False, indent=2))
    else:
        labels = {"pass": "通过", "fail": "失败", "manual": "人工"}
        for item in checks:
            print(f"[{labels[item.status]}] {item.title}: {item.detail}")
        print(f"\n汇总：通过 {summary['pass']}，失败 {summary['fail']}，人工 {summary['manual']}")

    return 1 if summary["fail"] or (args.strict and summary["manual"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
