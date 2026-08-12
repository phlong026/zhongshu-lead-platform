from __future__ import annotations

import asyncio

import httpx
import pytest

from scripts.claim_release_gate_v12 import verify_target_build_identity


def test_claim_release_gate_accepts_exact_target_build_sha() -> None:
    sha = "a" * 40

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/health/ready"
        return httpx.Response(
            200,
            json={"status": "ready", "version": "1.2.0", "build_sha": sha},
        )

    async def run() -> None:
        result = await verify_target_build_identity(
            "http://127.0.0.1:18080",
            sha,
            transport=httpx.MockTransport(handler),
        )
        assert result["build_sha"] == sha
        assert result["status"] == "ready"

    asyncio.run(run())


def test_claim_release_gate_rejects_wrong_target_build_sha() -> None:
    expected = "a" * 40
    actual = "b" * 40

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"status": "ready", "version": "1.2.0", "build_sha": actual},
        )

    async def run() -> None:
        with pytest.raises(ValueError, match="does not match candidate"):
            await verify_target_build_identity(
                "http://127.0.0.1:18080",
                expected,
                transport=httpx.MockTransport(handler),
            )

    asyncio.run(run())
