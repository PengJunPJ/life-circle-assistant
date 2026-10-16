"""Role-specific views assembled from fact slots and verified norm excerpts."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from ..contracts.facts import build_fact_catalog
from ..execution_ledger import record_version

AUDIENCES = {"resident": "居民", "community": "社区工作人员", "planner": "规划师"}


def project_rules_directory(module_path: Path | None = None) -> Path:
    module_path = module_path or Path(__file__).resolve()
    # 本地开发使用仓库ADR，容器只含应用包，使用随包逐字保留的项目规则。
    return next(
        (parent / "docs" / "adr" for parent in module_path.parents if (parent / "docs" / "adr").is_dir()),
        module_path.with_name("project_rules"),
    )


class NormRegistry:
    def __init__(self, sources: list[dict] | None = None):
        self.sources = sources if sources is not None else self._project_rules()

    @staticmethod
    def _project_rules():
        directory = project_rules_directory()
        sources = []
        for number in ("0006", "0011", "0010"):
            files = sorted(directory.glob(f"{number}-*.md"))
            if files:
                path = files[0]
                text = path.read_text(encoding="utf-8")
                sources.append(
                    {
                        "id": number,
                        "title": path.stem,
                        "version": "repository-current",
                        "source": str(path),
                        "scope": "项目规则",
                        "status": "verified_project_rule",
                        "text": text,
                        "sha256": hashlib.sha256(text.encode()).hexdigest(),
                    }
                )
        return sources

    @classmethod
    def from_env(cls):
        registry = cls()
        configured = os.getenv("LIFE_CIRCLE_NORMS_PATH", "").strip()
        if configured:
            records = json.loads(Path(configured).read_text(encoding="utf-8"))
            if not isinstance(records, list) or len(records) > 100:
                raise ValueError("规范库必须为不超过100份来源的JSON列表")
            for record in records:
                required = ("id", "title", "version", "source", "scope", "text", "verified_by", "verified_at")
                if not isinstance(record, dict) or any(
                    not isinstance(record.get(key), str) or not record[key].strip() for key in required
                ):
                    raise ValueError("外部规范必须有版本、适用范围、原始来源及审核人/时间")
                if len(record["text"]) > 100_000:
                    raise ValueError("规范文本超过长度预算")
                registry.sources.append(
                    {
                        **record,
                        "status": "human_verified_source",
                        "sha256": hashlib.sha256(record["text"].encode()).hexdigest(),
                    }
                )
        return registry

    def retrieve(self, query: str, limit: int = 4) -> list[dict]:
        record_version(
            "norm_sources",
            [{"id": item["id"], "version": item["version"], "sha256": item["sha256"]} for item in self.sources],
        )
        terms = set(re.findall(r"[a-z]+|[\u4e00-\u9fff]{2,}", query.lower()))
        ranked = []
        for source in self.sources:
            chunks = [part.strip() for part in re.split(r"\n\s*\n", source["text"]) if part.strip()]
            for index, chunk in enumerate(chunks):
                score = sum(term in chunk.lower() for term in terms)
                # Shared short Chinese tokens make paraphrases retrievable without an LLM.
                score += sum(token in chunk for token in ("设施", "步行", "评分", "盲区", "坐标") if token in query)
                if score:
                    ranked.append((score, source, index, chunk))
        ranked.sort(key=lambda value: (-value[0], value[1]["id"], value[2]))
        return [
            {key: source[key] for key in ("id", "title", "version", "source", "scope", "status", "sha256")}
            | {"chunk_id": f"{source['id']}:{index}", "excerpt": chunk[:1600], "text": chunk[:1600]}
            for _, source, index, chunk in ranked[:limit]
        ]


def build_audience_report(report: dict, audience: str, query: str = "", *, registry: NormRegistry | None = None):
    if audience not in AUDIENCES:
        raise ValueError("未知报告受众")
    catalog = build_fact_catalog(report)
    all_facts = catalog.allowed_claims()
    selected = [fact for fact in all_facts if fact["type"] in {"report", "category_score"}]
    if audience == "resident":
        selected = [
            fact for fact in selected if fact["slot"] in {"count", "nearest_walk_minutes", "critical_zone_count"}
        ]
    elif audience == "planner":
        selected += [fact for fact in all_facts if fact["type"] == "service_area" and fact["slot"] == "basis"][:16]
    norms = (registry or NormRegistry()).retrieve(query or "设施 步行 盲区 评分 坐标")
    observations = [
        {
            "text": fact["text"],
            "status": fact["status"],
            "claim": {key: fact[key] for key in ("report_id", "type", "id", "slot")},
            "evidence_refs": fact["evidence_refs"],
        }
        for fact in selected
    ]
    causes = []
    if (report.get("summary") or {}).get("critical_zone_count", 0):
        causes.append(
            {
                "text": "设施供给位置或步行连接条件可能影响可达性，需结合现场及完整设施台账核验。",
                "status": "hypothesis",
                "verified": False,
            }
        )
    measures = [
        {
            "text": item.get("title") or "复核服务设施配置",
            "status": "planning_proposal",
            "target_region_ids": item.get("target_region_ids", []),
            "candidate_ids": [candidate["id"] for candidate in item.get("candidate_locations", [])],
            "requires_simulation": True,
        }
        for item in report.get("recommendations", [])
    ]
    if audience == "resident":
        measures = [
            {
                "text": "可在地图查看现有设施和步行证据，并提交疑似停业、入口变化或围挡的待核验观察。",
                "status": "suggested_action",
                "requires_simulation": False,
            }
        ]
    conditions = [
        "设施来源范围及更新日期需要核验；报告中的未知结果保持未知。",
        "居民观察和OCR文本只有人工确认后才进入新目录，并需正式重算。",
    ]
    if audience == "planner":
        conditions += [
            "候选地块合法性、人口、容量、建设成本及土地条件需有可信来源。",
            "规范引用仅适用于标注范围；项目评分规则不等于法定规划标准。",
        ]
    elif audience == "community":
        conditions += ["优先组织短板区域、停业与入口变化的现场复核，保存审核依据和目录版本。"]
    return {
        "contract_version": "grounded-audience-report-v1",
        "report_id": report["report_id"],
        "audience": audience,
        "audience_label": AUDIENCES[audience],
        "title": f"{AUDIENCES[audience]}生活圈体检解读",
        "observations": observations,
        "possible_causes": causes,
        "measures": measures,
        "verification_conditions": conditions,
        "norms": norms,
        "citations": [
            {
                "chunk_id": item["chunk_id"],
                "source": item["source"],
                "version": item["version"],
                "sha256": item["sha256"],
            }
            for item in norms
        ],
        "source_report_quality": report.get("data_quality", {}),
        "disclosure": "观察来自固定报告事实槽位；原因仅为待核验假设，措施为规划建议，不改动原始报告和正式评分。",
    }
