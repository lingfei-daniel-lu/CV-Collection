"""LLM client configuration and chat helper for the current Poe-based pipeline."""

from __future__ import annotations

import os, sys, time
from dataclasses import dataclass
from typing import Optional

from openai import OpenAI

MAX_RETRIES = 5
POE_BASE_URL = "https://api.poe.com/v1"


def _load_local_api_keys() -> dict[str, str]:
    try:
        from local_api_keys import API_KEYS as local_api_keys  # type: ignore
    except Exception:
        return {}
    if not isinstance(local_api_keys, dict):
        raise TypeError("local_api_keys.API_KEYS must be a dict[str, str].")
    return {str(k): str(v).strip() for k, v in local_api_keys.items() if str(v).strip()}
def _require_api_key(name: str) -> str:
    value = LOCAL_API_KEYS.get(name) or os.getenv(name, "").strip()
    if value:
        return value
    raise RuntimeError(
        f"Missing API key '{name}'. Add it to local_api_keys.py "
        f"or set environment variable {name}."
    )


LOCAL_API_KEYS = _load_local_api_keys()
POE_API_KEY = _require_api_key("POE_API_KEY")


@dataclass(frozen=True)
class ModelConfig:
    key: str
    model: str
    api_key: str
    base_url: str | None = None
    temperature: float = 0.4

    def build_client(self) -> OpenAI:
        kwargs = {"api_key": self.api_key}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        return OpenAI(**kwargs)

    def resolved_model(self) -> str:
        return self.model


MODEL_CONFIGS: dict[str, ModelConfig] = {
    "deepseek": ModelConfig(
        key="deepseek",
        # Original direct DeepSeek call, kept for reference:
        # model="deepseek-reasoner",
        # api_key=_require_api_key("DEEPSEEK_API_KEY"),
        # base_url="https://api.deepseek.com",
        model="deepseek-v3.2",
        api_key=POE_API_KEY,
        base_url=POE_BASE_URL,
    ),
    "kimi": ModelConfig(
        key="kimi",
        # Original direct Kimi(Moonshot) call, kept for reference:
        # model="kimi-k2-thinking",
        # api_key=_require_api_key("KIMI_API_KEY"),
        # base_url="https://api.moonshot.ai/v1",
        model="kimi-k2.5",
        api_key=POE_API_KEY,
        base_url=POE_BASE_URL,
    ),
    # Poe models (fixed model names).
    "gpt": ModelConfig(
        key="gpt",
        # model="gpt-5.2",
        model="gpt-5-mini",
        api_key=POE_API_KEY,
        base_url=POE_BASE_URL,
    ),
    "claude": ModelConfig(
        key="claude",
        # model="claude-opus-4-6"
        model="claude-haiku-4-5",
        api_key=POE_API_KEY,
        base_url=POE_BASE_URL,
    ),
    "gemini": ModelConfig(
        key="gemini",
        # model="gemini-3-pro",
        model="gemini-3-flash",
        api_key=POE_API_KEY,
        base_url=POE_BASE_URL,
    ),
}


class ModelClient:
    def __init__(self, config: ModelConfig):
        self.config = config
        self.client = config.build_client()
        self.model = self.config.resolved_model()

    def chat_messages(self, messages: list[dict[str, str]]) -> Optional[str]:
        """Call the configured chat model with arbitrary message payloads."""
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.client.chat.completions.create(
                    model=self.model,
                    temperature=self.config.temperature,
                    messages=messages,
                )
                return resp.choices[0].message.content.strip()

            except Exception as e:
                if attempt == MAX_RETRIES:
                    raise
                wait = 2 ** attempt
                print(
                    f"⚠️  {self.config.key} API error: {e}. Retrying in {wait}s …",
                    file=sys.stderr,
                )
                time.sleep(wait)

        return None

def get_model_client(key: str) -> ModelClient:
    try:
        config = MODEL_CONFIGS[key]
    except KeyError:
        raise KeyError(f"Unknown model key '{key}'. Choose from {', '.join(MODEL_CONFIGS)}")
    return ModelClient(config)
