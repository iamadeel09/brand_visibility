"""AI model scanner: sends neutral buyer-intent questions to LLM providers.

OpenAI is the primary provider (AsyncOpenAI). Anthropic (Claude) and Gemini
are optional and only used when listed in GEO_PROVIDERS and configured.
Failures are returned as ScanResult(ok=False) - never faked as live answers.

Environment:
    OPENAI_API_KEY, OPENAI_MODEL (default gpt-4o-mini)
    ANTHROPIC_API_KEY, ANTHROPIC_MODEL   (optional provider "anthropic")
    GEMINI_API_KEY, GEMINI_MODEL         (optional provider "gemini")
    GEO_PROVIDERS   comma list, default "openai"
    GEO_TIMEOUT     seconds per request, default 30
    GEO_CONCURRENCY max concurrent requests, default 5
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

SYSTEM_PROMPT = (
    "You are a helpful, neutral assistant answering a buyer's question. "
    "Give an honest, balanced answer and name specific products or companies "
    "where relevant."
)
MAX_ANSWER_CHARS = 8000
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5"
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"
KNOWN_PROVIDERS = ("openai", "anthropic", "gemini")

_KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


@dataclass
class ScanResult:
    provider: str
    query: str
    answer: str = ""
    ok: bool = False
    error: str = ""


def sanitize_text(text) -> str:
    """Treat model output as untrusted: coerce to str, drop control chars, cap length."""
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    return text.strip()[:MAX_ANSWER_CHARS]


def redact_secrets(message: str) -> str:
    """Remove anything that looks like an API key (and any configured key) from text."""
    message = str(message)
    for env in _KEY_ENV.values():
        secret = os.environ.get(env, "")
        if secret and len(secret) >= 6:
            message = message.replace(secret, "[REDACTED]")
    message = re.sub(r"\b(sk|key|AIza)[-_A-Za-z0-9]{12,}", "[REDACTED]", message)
    return message[:300]


def configured_providers() -> list[str]:
    raw = os.environ.get("GEO_PROVIDERS", "openai")
    names = [p.strip().lower() for p in raw.split(",") if p.strip()]
    seen: list[str] = []
    for n in names:
        if n in KNOWN_PROVIDERS and n not in seen:
            seen.append(n)
    return seen or ["openai"]


def _timeout() -> float:
    try:
        return max(1.0, float(os.environ.get("GEO_TIMEOUT", "30")))
    except ValueError:
        return 30.0


def _concurrency() -> int:
    try:
        return max(1, int(os.environ.get("GEO_CONCURRENCY", "5")))
    except ValueError:
        return 5


# --------------------------------------------------------------------------
# Providers: each returns the answer text or raises.
# --------------------------------------------------------------------------
async def _ask_openai(query: str, api_key: str, timeout: float) -> str:
    try:
        from openai import AsyncOpenAI
    except ImportError as exc:
        raise RuntimeError("openai package is not installed") from exc
    model = os.environ.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
    client = AsyncOpenAI(api_key=api_key, timeout=timeout, max_retries=1)
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": query},
            ],
        )
    finally:
        await client.close()
    return resp.choices[0].message.content or ""


async def _ask_anthropic(query: str, api_key: str, timeout: float) -> str:
    try:
        from anthropic import AsyncAnthropic
    except ImportError as exc:
        raise RuntimeError("anthropic package is not installed") from exc
    model = os.environ.get("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL)
    client = AsyncAnthropic(api_key=api_key, timeout=timeout, max_retries=1)
    resp = await client.messages.create(
        model=model,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": query}],
    )
    return "".join(getattr(b, "text", "") for b in resp.content)


def _gemini_sync(query: str, api_key: str, timeout: float) -> str:
    model = os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = json.dumps(
        {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": query}]}],
        }
    ).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (fixed https host)
        data = json.loads(r.read().decode("utf-8", "replace"))
    parts = data["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts)


async def _ask_gemini(query: str, api_key: str, timeout: float) -> str:
    return await asyncio.to_thread(_gemini_sync, query, api_key, timeout)


_PROVIDER_FUNCS = {
    "openai": _ask_openai,
    "anthropic": _ask_anthropic,
    "gemini": _ask_gemini,
}


async def scan_one(provider: str, query: str, semaphore: asyncio.Semaphore | None = None) -> ScanResult:
    """Ask one provider one question. Never raises; failures become ok=False."""
    api_key = os.environ.get(_KEY_ENV.get(provider, ""), "").strip()
    if not api_key:
        return ScanResult(provider, query, error=f"{_KEY_ENV.get(provider, provider)} is not set")
    func = _PROVIDER_FUNCS.get(provider)
    if func is None:
        return ScanResult(provider, query, error=f"unknown provider '{provider}'")
    timeout = _timeout()
    try:
        if semaphore is None:
            raw = await asyncio.wait_for(func(query, api_key, timeout), timeout + 5)
        else:
            async with semaphore:
                raw = await asyncio.wait_for(func(query, api_key, timeout), timeout + 5)
    except asyncio.TimeoutError:
        return ScanResult(provider, query, error=f"request timed out after {timeout:.0f}s")
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - any provider failure is a scan failure
        return ScanResult(provider, query, error=f"{type(exc).__name__}: {redact_secrets(exc)}")
    answer = sanitize_text(raw)
    if not answer:
        return ScanResult(provider, query, error="empty response")
    return ScanResult(provider, query, answer=answer, ok=True)


async def scan_queries(queries: list[str], providers: list[str] | None = None) -> list[ScanResult]:
    """Concurrently scan every (provider, query) pair."""
    providers = providers or configured_providers()
    sem = asyncio.Semaphore(_concurrency())
    tasks = [scan_one(p, q, sem) for p in providers for q in queries]
    return list(await asyncio.gather(*tasks))


def run_scan(queries: list[str], providers: list[str] | None = None) -> list[ScanResult]:
    """Synchronous wrapper; safe to call even if an event loop is already running."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(scan_queries(queries, providers))
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(scan_queries(queries, providers))).result()
