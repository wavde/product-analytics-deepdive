"""Pluggable model runners.

A runner turns (system prompt, message list) into one assistant reply plus token counts.
Live runners use the standard library only (no SDK dependency) and read their API key
from an environment variable. ``ReplayRunner`` re-feeds saved replies so a saved run can
be re-executed offline; ``CallableRunner`` wraps a Python function for tests.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol


@dataclass
class Completion:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0


class ModelRunner(Protocol):
    provider: str
    model: str

    def complete(self, system: str, messages: list[dict]) -> Completion: ...


@dataclass(frozen=True)
class Pricing:
    """USD per million tokens. Supplied by the caller; prices change too often to hardcode."""

    input_per_mtok: float
    output_per_mtok: float

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens * self.input_per_mtok + output_tokens * self.output_per_mtok) / 1e6


def _post_json(url: str, headers: dict, body: dict, timeout: float, retries: int = 3) -> dict:
    data = json.dumps(body).encode("utf-8")
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            if err.code in (429, 500, 502, 503, 529) and attempt < retries:
                time.sleep(2**attempt * 5)
                continue
            detail = err.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"HTTP {err.code} from {url}: {detail}") from err
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt < retries:
                time.sleep(2**attempt * 5)
                continue
            raise
    raise RuntimeError("unreachable")


def _require_key(env_var: str) -> str:
    key = os.environ.get(env_var)
    if not key:
        raise RuntimeError(f"Set {env_var} to use this runner.")
    return key


@dataclass
class OpenAICompatibleRunner:
    """Any endpoint that speaks the OpenAI chat-completions format."""

    model: str
    base_url: str = "https://api.openai.com/v1"
    api_key_env: str = "OPENAI_API_KEY"
    temperature: float = 0.0
    max_output_tokens: int = 2000
    timeout: float = 120.0
    provider: str = "openai-compatible"

    def complete(self, system: str, messages: list[dict]) -> Completion:
        key = _require_key(self.api_key_env)
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "temperature": self.temperature,
            "max_tokens": self.max_output_tokens,
        }
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        out = _post_json(f"{self.base_url.rstrip('/')}/chat/completions", headers, body,
                         self.timeout)
        usage = out.get("usage") or {}
        return Completion(
            text=out["choices"][0]["message"]["content"] or "",
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
        )


@dataclass
class AnthropicRunner:
    model: str
    api_key_env: str = "ANTHROPIC_API_KEY"
    temperature: float = 0.0
    max_output_tokens: int = 2000
    timeout: float = 120.0
    base_url: str = "https://api.anthropic.com/v1"
    provider: str = "anthropic"

    def complete(self, system: str, messages: list[dict]) -> Completion:
        key = _require_key(self.api_key_env)
        body = {
            "model": self.model,
            "system": system,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_output_tokens,
        }
        headers = {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        out = _post_json(f"{self.base_url.rstrip('/')}/messages", headers, body, self.timeout)
        usage = out.get("usage") or {}
        text = "".join(b.get("text", "") for b in out.get("content", []) if b.get("type") == "text")
        return Completion(
            text=text,
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
        )


class ReplayExhausted(RuntimeError):
    """The harness asked for more turns than the saved run contains."""


class ReplayRunner:
    """Replays saved assistant replies in order. Used to re-execute saved runs offline."""

    provider = "replay"

    def __init__(self, replies: Iterable[Completion], model: str = "replay"):
        self._replies = list(replies)
        self._i = 0
        self.model = model

    def complete(self, system: str, messages: list[dict]) -> Completion:
        if self._i >= len(self._replies):
            raise ReplayExhausted("the harness asked for more turns than were saved")
        reply = self._replies[self._i]
        self._i += 1
        return reply

    @property
    def exhausted(self) -> bool:
        return self._i == len(self._replies)


class CallableRunner:
    """Wraps ``fn(system, messages) -> str``. For harness tests, never for reported results."""

    provider = "callable"

    def __init__(self, fn: Callable[[str, list[dict]], str], model: str = "callable"):
        self._fn = fn
        self.model = model

    def complete(self, system: str, messages: list[dict]) -> Completion:
        return Completion(text=self._fn(system, messages))
