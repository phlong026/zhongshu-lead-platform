from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

import httpx

from ..core.config import get_settings
from ..core.errors import AppError

settings = get_settings()


@dataclass(frozen=True)
class FeishuRecord:
    record_id: str
    fields: dict[str, Any]


class FeishuClient:
    def __init__(self, *, transport: httpx.BaseTransport | None = None) -> None:
        self._token: str | None = None
        self._token_expires_at: datetime | None = None
        self._client = httpx.Client(transport=transport, timeout=30)

    def diagnostics(self) -> dict[str, Any]:
        return {
            "configured": bool(settings.feishu_app_id and settings.feishu_app_secret and settings.feishu_app_token and settings.feishu_table_id),
            "dev_mock": settings.feishu_dev_mock,
            "app_token_configured": bool(settings.feishu_app_token),
            "table_id_configured": bool(settings.feishu_table_id),
        }

    def _request(self, method: str, url: str, *, retry: int = 3, auth: bool = False, **kwargs: Any) -> dict[str, Any]:
        last_error: Exception | None = None
        base_headers = dict(kwargs.pop("headers", {}) or {})
        for attempt in range(retry):
            try:
                headers = dict(base_headers)
                if auth:
                    headers["Authorization"] = f"Bearer {self._tenant_token()}"
                response = self._client.request(method, url, headers=headers, **kwargs)
                if response.status_code == 401 and auth:
                    self._token = None
                    self._token_expires_at = None
                    raise httpx.HTTPStatusError("expired feishu token", request=response.request, response=response)
                if response.status_code == 429 or response.status_code >= 500:
                    raise httpx.HTTPStatusError("retryable feishu response", request=response.request, response=response)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("invalid JSON object")
                return payload
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt + 1 < retry:
                    time.sleep(0.2 * (2**attempt))
        raise AppError("FEISHU_UNAVAILABLE", "飞书接口暂时不可用", 502, {"error": str(last_error)}) from last_error

    def _tenant_token(self) -> str:
        if self._token and self._token_expires_at and self._token_expires_at > datetime.now(timezone.utc) + timedelta(minutes=5):
            return self._token
        if not settings.feishu_app_id or not settings.feishu_app_secret:
            raise AppError("FEISHU_NOT_CONFIGURED", "飞书应用尚未配置", 503)
        payload = self._request(
            "POST",
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": settings.feishu_app_id, "app_secret": settings.feishu_app_secret},
        )
        if payload.get("code") != 0 or not payload.get("tenant_access_token"):
            raise AppError("FEISHU_TOKEN_FAILED", "获取飞书访问令牌失败", 502, payload)
        self._token = str(payload["tenant_access_token"])
        self._token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(payload.get("expire", 7200)))
        return self._token

    def list_records(self, page_token: str | None = None, page_size: int = 200) -> tuple[list[FeishuRecord], str | None, bool]:
        if settings.feishu_dev_mock:
            return [], None, False
        if not settings.feishu_app_token or not settings.feishu_table_id:
            raise AppError("FEISHU_TABLE_NOT_CONFIGURED", "飞书多维表格尚未配置", 503)
        params: dict[str, Any] = {"page_size": min(max(page_size, 1), 500)}
        if page_token:
            params["page_token"] = page_token
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{settings.feishu_app_token}/tables/{settings.feishu_table_id}/records"
        payload = self._request("GET", url, auth=True, params=params)
        if payload.get("code") != 0:
            raise AppError("FEISHU_LIST_FAILED", "读取飞书多维表格失败", 502, payload)
        data = payload.get("data") or {}
        records = [
            FeishuRecord(record_id=str(item["record_id"]), fields=item.get("fields") or {})
            for item in data.get("items") or []
            if item.get("record_id")
        ]
        return records, data.get("page_token"), bool(data.get("has_more"))

    def iter_records(self, *, page_size: int = 200, max_pages: int = 100) -> Iterator[FeishuRecord]:
        page_token: str | None = None
        seen_tokens: set[str] = set()
        for _ in range(max_pages):
            records, next_token, has_more = self.list_records(page_token, page_size)
            yield from records
            if not has_more:
                return
            if not next_token or next_token in seen_tokens:
                raise AppError("FEISHU_PAGINATION_INVALID", "飞书分页游标异常", 502)
            seen_tokens.add(next_token)
            page_token = next_token
        raise AppError("FEISHU_PAGE_LIMIT", "飞书同步页数超过安全上限", 409, {"max_pages": max_pages})

    def write_back(self, record_id: str, fields: dict[str, Any]) -> None:
        if settings.feishu_dev_mock:
            return
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{settings.feishu_app_token}/tables/{settings.feishu_table_id}/records/{record_id}"
        payload = self._request("PUT", url, auth=True, json={"fields": fields})
        if payload.get("code") != 0:
            raise AppError("FEISHU_WRITEBACK_FAILED", "飞书状态回写失败", 502, payload)
