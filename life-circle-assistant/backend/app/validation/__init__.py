"""真实社区基准数据与评估工具。"""

from .benchmarks import (
    CommunityBenchmark,
    evaluate_benchmark,
    generate_benchmark_template,
    render_markdown_report,
)

__all__ = [
    "CommunityBenchmark",
    "evaluate_benchmark",
    "generate_benchmark_template",
    "render_markdown_report",
]

