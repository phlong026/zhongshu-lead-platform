from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from ..core.config import get_settings
from ..core.errors import AppError

settings = get_settings()


@dataclass(frozen=True)
class FeishuRecord:
    record_id: str
    fields: dict[str, Any]


class FeishuClient:
    def __init__(self) -> None:
        self._token: str | None = None
        self._token_expires_at: datetime | None = None

    def _tenant_token(self) -> str:
        if self._token and self._token_expires_at and self._token_expires_at > datetime.now(timezone.utc) + timedelta(minutes=5):
            return self._token
        if not settings.feishu_app_id or not settings.feishu_app_secret:
            raise AppError("FEISHU_NOT_CONFIGURED", "飞书应用尚未配置", 503)
        response = httpx.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": settings.feishu_app_id, "app_secret": settings.feishu_app_secret},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            raise AppError("FEISHU_TOKEN_FAILED", "获取飞书访问令牌失败", 502, payload)
        self._token = payload["tenant_access_token"]
        self._token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(payload.get("expire", 7200)))
        return self._token

    def list_records(self, page_token: str | None = None, page_size: int = 200) -> tuple[list[FeishuRecord], str | None, bool]:
        if settings.feishu_dev_mock:
            return [], None, False
        token = self._tenant_token()
        params: dict[str, Any] = {"page_size": min(page_size, 500)}
        if page_token:
            params["page_token"] = page_token
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{settings.feishu_app_token}/tables/{settings.feishu_table_id}/records"
        response = httpx.get(url, headers={"Authorization": f"Bearer {token}"}, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            raise AppError("FEISHU_LIST_FAILED", "读取飞书多维表格失败", 502, payload)
        data = payload.get("data") or {}
        records = [FeishuRecord(record_id=item["record_id"], fields=item.get("fields") or {}) for item in data.get("items") or []]
        return records, data.get("page_token"), bool(data.get("has_more"))

    def write_back(self, record_id: str, fields: dict[str, Any]) -> None:
        if settings.feishu_dev_mock:
            return
        token = self._tenant_token()
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{settings.feishu_app_token}/tables/{settings.feishu_table_id}/records/{record_id}"
        response = httpx.put(url, headers={"Authorization": f"Bearer {token}"}, json={"fields": fields}, timeout=20)
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 0:
            raise AppError("FEISHU_WRITEBACK_FAILED", "飞书状态回写失败", 502, payload)
