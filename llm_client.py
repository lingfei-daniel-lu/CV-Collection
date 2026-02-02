"""
LLM client configuration and call helper, supporting multiple providers.
"""

from __future__ import annotations

import os, sys, time
from dataclasses import dataclass
from typing import Optional

from openai import OpenAI

MAX_RETRIES = 5


@dataclass(frozen=True)
class ModelConfig:
    key: str
    model: str
    api_key_env: str  # Env var name OR literal key
    base_url: str | None = None
    temperature: float = 0.4
    model_env: str | None = None  # Optional env var to override the model name

    def build_client(self) -> OpenAI:
        api_key = os.getenv(self.api_key_env)
        # If env var is not set, fall back to the configured value as a literal key.
        if not api_key:
            api_key = self.api_key_env
        if not api_key:
            raise RuntimeError(f"Set env var {self.api_key_env} for {self.key}")
        kwargs = {"api_key": api_key}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        return OpenAI(**kwargs)

    def resolved_model(self) -> str:
        if self.model_env:
            model = os.getenv(self.model_env, "").strip()
            if model:
                return model
        return self.model


MODEL_CONFIGS: dict[str, ModelConfig] = {
    "deepseek": ModelConfig(
        key="deepseek",
        model="deepseek-chat",
        api_key_env="sk-6f7094ece175423c992b4e231dcfbe49",
        base_url="https://api.deepseek.com",
    ),
    "kimi": ModelConfig(
        key="kimi",
        model="kimi-k2-0905-preview",
        api_key_env="sk-KrRE2LB9Fph3WP9qdl0zFkhY2e3K7AV7svsspivea58PlJV2",
        base_url="https://api.moonshot.ai/v1",
    ),
    # Poe provides an OpenAI-compatible API endpoint
    "poe": ModelConfig(
        key="poe",
        model="gpt-5.2",
        model_env="POE_MODEL",
        api_key_env="IuB8CmzLrdDGrXpxIAxQSnOdwvX3MqrsjbIBKiChSuU",
        base_url="https://api.poe.com/v1",
    ),
}


class ModelClient:
    def __init__(self, config: ModelConfig):
        self.config = config
        self.client = config.build_client()

    def chat_completion(self, cv_text: str, prompt: str) -> Optional[str]:
        """Call the configured chat model with retries."""
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = self.client.chat.completions.create(
                    model=self.config.resolved_model(),
                    temperature=self.config.temperature,
                    messages=[
                        {"role": "user", "content": prompt},
                        {"role": "user", "content": cv_text},
                    ],
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
