from __future__ import annotations

import os
from dataclasses import dataclass

import httpx


class DeepSeekConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class DeepSeekClient:
    api_key: str
    model: str = "deepseek-chat"
    base_url: str = "https://api.deepseek.com"

    @classmethod
    def from_env(cls) -> "DeepSeekClient":
        api_key = (
            os.getenv("deepseek_key")
            or os.getenv("DEEPSEEK_API_KEY")
            or os.getenv("DEEPSEEK_KEY")
        )
        if not api_key:
            raise DeepSeekConfigError(
                "DeepSeek API key not found. Set deepseek_key, DEEPSEEK_API_KEY, or DEEPSEEK_KEY."
            )
        return cls(
            api_key=api_key,
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/"),
        )

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 260,
        temperature: float = 0.35,
    ) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        return data["choices"][0]["message"]["content"]


def deepseek_key_loaded() -> bool:
    return bool(
        os.getenv("deepseek_key")
        or os.getenv("DEEPSEEK_API_KEY")
        or os.getenv("DEEPSEEK_KEY")
    )
