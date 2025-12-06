import httpx
from typing import Optional
from config import settings


class OpenRouterClient:
    BASE_URL = "https://openrouter.ai/api/v1"

    # ONLY Grok and Gemini models - per user request
    MODELS = {
        "ingestion": "x-ai/grok-4.1-fast",  # Grok - fast, good for search result processing
        "orchestrator": "google/gemini-2.5-flash-lite",  # Gemini - fast, multimodal, cheap
        "fast": "x-ai/grok-4.1-fast",  # Grok - fastest option
        "structured": "google/gemini-2.5-flash-lite",  # Gemini - good for structured data extraction
    }

    COSTS = {
        "ingestion": 0.00010,  # Grok pricing
        "orchestrator": 0.00005,  # Gemini pricing
        "fast": 0.00010,  # Grok pricing
        "structured": 0.00005,  # Gemini pricing
    }

    def __init__(self):
        self.api_key = settings.openrouter_api_key
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://swoopserviceauto.com",
            "X-Title": "Swoop Intelligence",
        }

    async def chat_completion(
        self,
        model_key: str,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 2000,
        enable_reasoning: bool = False,
        **kwargs,
    ) -> tuple[str, float]:
        """
        Returns: (response_text, estimated_cost)
        """
        model_id = self.MODELS.get(model_key)
        if not model_id:
            raise ValueError(f"Unknown model key: {model_key}")

        payload = {
            "model": model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs,
        }

        # Note: OpenRouter doesn't have a "reasoning" parameter
        # Grok has reasoning built-in, no need to enable it

        # Increase timeout for free tier models (can be slow)
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(
                f"{self.BASE_URL}/chat/completions", headers=self.headers, json=payload
            )
            response.raise_for_status()
            data = response.json()

            content = data["choices"][0]["message"]["content"]
            cost = self.COSTS.get(model_key, 0.0)

            return content, cost


openrouter = OpenRouterClient()
