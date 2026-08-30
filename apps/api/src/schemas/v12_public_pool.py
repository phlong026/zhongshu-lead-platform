from __future__ import annotations

from pydantic import BaseModel

from ..services.public_pool_v12 import PublicPoolTarget


class PublicPoolFeishuImportBody(BaseModel):
    target_pool: PublicPoolTarget = PublicPoolTarget.PUBLIC_POOL
