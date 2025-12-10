"""
LLM client configuration and call helper.
"""

from __future__ import annotations

import os, sys, time
from typing import Optional

from openai import OpenAI

# Model and retry settings are grouped here for easy swapping between providers.
MODEL_NAME  = "deepseek-chat"
TEMPERATURE = 0.4
MAX_RETRIES = 5
BASE_URL    = "https://api.deepseek.com"

# Prefer environment variable; fall back to the existing key if present.
API_KEY = os.getenv("DEEPSEEK_API_KEY") or "sk-6f7094ece175423c992b4e231dcfbe49"

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)


def chat_completion(cv_text: str, prompt: str) -> Optional[str]:
    """Call the configured chat model with retries."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = client.chat.completions.create(
                model=MODEL_NAME,
                temperature=TEMPERATURE,
                messages=[
                    {"role": "user", "content": prompt},
                    {"role": "user", "content": cv_text},
                ]
            )
            return resp.choices[0].message.content.strip()

        except Exception as e:
            if attempt == MAX_RETRIES:
                raise
            wait = 2 ** attempt
            print(f"⚠️  API error: {e}. Retrying in {wait}s …", file=sys.stderr)
            time.sleep(wait)

    return None
