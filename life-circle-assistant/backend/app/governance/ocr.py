"""Image text is unverified source material, never a facility fact."""

from __future__ import annotations

import base64
import os

import httpx

from ..execution_ledger import charge_external, record_version

MAX_IMAGE_BYTES = 4 * 1024 * 1024


def validate_image(encoded: str, mime_type: str) -> bytes:
    if len(encoded) > MAX_IMAGE_BYTES * 4 // 3 + 8:
        raise ValueError("图片超过4MB")
    try:
        image = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ValueError("图片Base64无效") from exc
    prefixes = {"image/png": b"\x89PNG\r\n\x1a\n", "image/jpeg": b"\xff\xd8\xff", "image/webp": b"RIFF"}
    if (
        not image
        or len(image) > MAX_IMAGE_BYTES
        or mime_type not in prefixes
        or not image.startswith(prefixes[mime_type])
    ):
        raise ValueError("图片格式必须为有效PNG、JPEG或WebP")
    if mime_type == "image/webp" and image[8:12] != b"WEBP":
        raise ValueError("WebP文件头无效")
    return image


class CompatibleOCRProvider:
    """JSON OCR contract usable with Chinese OCR/self-hosted services."""

    def __init__(self, endpoint: str, api_key: str = "", *, client=None):
        self.endpoint = endpoint
        self._client = client or httpx.AsyncClient(
            timeout=15, headers={"Authorization": f"Bearer {api_key}"} if api_key else {}
        )
        self.calls = 0

    async def extract(self, image_base64: str, mime_type: str) -> str:
        validate_image(image_base64, mime_type)
        record_version("ocr_contract", "chinese-ocr-json-v1")
        charge_external("ocr_http_attempts")
        self.calls += 1
        response = await self._client.post(
            self.endpoint, json={"image_base64": image_base64, "mime_type": mime_type, "language": "zh"}
        )
        response.raise_for_status()
        payload = response.json()
        text = payload.get("text") if isinstance(payload, dict) else None
        if not isinstance(text, str) or len(text) > 5000:
            raise ValueError("OCR响应文本无效")
        return text

    async def close(self):
        await self._client.aclose()


def create_ocr_provider_from_env():
    if os.getenv("OBSERVATION_OCR_ENABLED", "false").lower() not in {"true", "1", "yes"}:
        return None
    endpoint = os.getenv("OBSERVATION_OCR_ENDPOINT", "").strip()
    if not endpoint:
        raise ValueError("启用OCR时必须配置服务地址")
    return CompatibleOCRProvider(endpoint, os.getenv("OBSERVATION_OCR_API_KEY", ""))
