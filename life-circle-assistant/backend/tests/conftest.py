import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# 后端测试必须与开发者本机的正式百度配置隔离，避免回归测试消耗线上配额，
# 也确保依赖本地快照的断言在任何环境中都保持确定性。
os.environ["BAIDU_MAP_MODE"] = "mock"
os.environ["BAIDU_MAP_QPS"] = "0"
os.environ["WALKING_QPS"] = "0"
os.environ.pop("BAIDU_MAP_AK", None)
os.environ.pop("BAIDU_MAP_SECRET", None)
os.environ["AMAP_VALIDATION_ENABLED"] = "false"
os.environ["AMAP_QPS"] = "0"
os.environ.pop("AMAP_WEB_SERVICE_KEY", None)
# 模型测试同样必须隔离本机 .env；专项测试通过注入 FakeProvider 验证协议。
os.environ["LLM_ENABLED"] = "false"
os.environ.pop("LLM_API_KEY", None)
# 中文嵌入、OCR与原生等时圈也须显式注入模拟客户端；不继承本机付费配置。
os.environ["SEMANTIC_EMBEDDING_ENABLED"] = "false"
os.environ["OBSERVATION_OCR_ENABLED"] = "false"
os.environ["BAIDU_NATIVE_ISOCHRONE_ENABLED"] = "false"
for name in (
    "SEMANTIC_EMBEDDING_PROVIDER",
    "SEMANTIC_EMBEDDING_BASE_URL",
    "SEMANTIC_EMBEDDING_MODEL",
    "SEMANTIC_EMBEDDING_API_KEY",
    "SEMANTIC_EMBEDDING_MODEL_PATH",
    "OBSERVATION_OCR_ENDPOINT",
    "OBSERVATION_OCR_API_KEY",
    "LIFE_CIRCLE_NORMS_PATH",
):
    os.environ.pop(name, None)
