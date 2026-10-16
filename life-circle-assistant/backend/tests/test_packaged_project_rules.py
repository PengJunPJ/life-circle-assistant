import os
import shutil
import subprocess
import sys
from pathlib import Path

from app.governance.reports import project_rules_directory


def test_project_rules_work_at_shallow_container_path_and_match_repository():
    assert project_rules_directory(Path("/app/app/governance/reports.py")) == Path("/app/app/governance/project_rules")
    backend = Path(__file__).resolve().parents[1]
    package = backend / "app" / "governance" / "project_rules"
    repository = backend.parents[1] / "docs" / "adr"
    for bundled in package.glob("*.md"):
        assert bundled.read_bytes() == (repository / bundled.name).read_bytes(), "项目规则副本必须与ADR逐字一致"
    assert len(list(package.glob("*.md"))) == 3


def test_application_starts_with_only_docker_copy_contents(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    packaged_root = tmp_path / "container"
    shutil.copytree(backend / "app", packaged_root / "app", ignore=shutil.ignore_patterns("__pycache__"))
    (packaged_root / "data").mkdir()
    shutil.copyfile(backend / "data" / "baidu_snapshot.json", packaged_root / "data" / "baidu_snapshot.json")
    env = {
        **os.environ,
        "PYTHONPATH": str(packaged_root),
        "LIFE_CIRCLE_DATABASE_PATH": str(packaged_root / "data" / "test.sqlite"),
        "LIFE_CIRCLE_SEED_WALKING_CACHE": "0",
        "LIFE_CIRCLE_NORMS_PATH": "",
    }
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from fastapi.testclient import TestClient\n"
            "from app.main import app\n"
            "with TestClient(app) as client:\n"
            " assert client.get('/api/health').status_code == 200\n"
            " assert len(app.state.norm_registry.sources) == 3\n"
            " assert all('/project_rules/' in s['source'] for s in app.state.norm_registry.sources)\n",
        ],
        cwd=packaged_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
