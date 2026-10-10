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
