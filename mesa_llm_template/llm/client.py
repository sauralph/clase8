"""
Cliente LLM unificado para la actividad práctica.

Provee un solo método `complete_json(prompt) -> dict` y maneja **4 backends**:

  - `openai`     — OpenAI Chat Completions (necesita OPENAI_API_KEY)
  - `anthropic`  — Anthropic Messages       (necesita ANTHROPIC_API_KEY)
  - `ollama`     — Ollama local             (necesita `ollama serve` corriendo)
  - `mock`       — fallback offline         (siempre disponible)

Selección automática (por defecto):
  OPENAI_API_KEY  → openai
  ANTHROPIC_API_KEY → anthropic
  OLLAMA_HOST     → ollama
  caso contrario  → mock

Uso típico:

    from llm import LLMClient
    client = LLMClient(provider="auto")        # detecta solo
    response = client.complete_json(prompt)    # dict listo para usar
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

import requests

from . import mock


@dataclass
class LLMResponse:
    text: str
    parsed: dict[str, Any] | None
    provider: str
    model: str | None = None


class LLMClient:
    def __init__(
        self,
        provider: str = "auto",
        model: str | None = None,
        temperature: float = 0.7,
        timeout: float | None = None,
    ):
        self.temperature = temperature

        if provider == "auto":
            provider = self._auto_detect()

        self.provider = provider
        self.model = model or self._default_model(provider)

        # Default timeouts: Ollama necesita más por el cold-start del modelo
        if timeout is None:
            timeout = {
                "openai":    60.0,
                "anthropic": 60.0,
                "ollama":    180.0,   # 1ra carga del modelo a VRAM puede tardar
                "mock":      5.0,
            }.get(provider, 60.0)
        self.timeout = timeout

    # ------------------------------------------------------------- helpers
    @staticmethod
    def _auto_detect() -> str:
        if os.environ.get("OPENAI_API_KEY"):
            return "openai"
        if os.environ.get("ANTHROPIC_API_KEY"):
            return "anthropic"
        if os.environ.get("OLLAMA_HOST"):
            return "ollama"
        return "mock"

    @staticmethod
    def _default_model(provider: str) -> str | None:
        return {
            "openai":    os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            "anthropic": os.environ.get("ANTHROPIC_MODEL", "claude-3-5-haiku-latest"),
            "ollama":    os.environ.get("OLLAMA_MODEL", "llama3.2"),
            "mock":      "mock-rule-based",
        }.get(provider)

    # ----------------------------------------------------------------- API
    def complete_json(
        self,
        prompt: str,
        salt: int = 0,
    ) -> LLMResponse:
        """
        Pide al LLM una respuesta y la parsea como JSON.
        `salt` solo afecta al mock (lo usa de semilla determinística).
        """
        if self.provider == "mock":
            text = mock.respond(prompt, salt=salt)
        elif self.provider == "openai":
            text = self._call_openai(prompt)
        elif self.provider == "anthropic":
            text = self._call_anthropic(prompt)
        elif self.provider == "ollama":
            text = self._call_ollama(prompt)
        else:
            raise ValueError(f"provider desconocido: {self.provider}")

        parsed = _safe_parse_json(text)
        return LLMResponse(
            text=text, parsed=parsed,
            provider=self.provider, model=self.model,
        )

    # ----------------------------------------------------- backends reales
    def _call_openai(self, prompt: str) -> str:
        api_key = os.environ["OPENAI_API_KEY"]
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system",
                 "content": "Sos un agente de simulación. Respondés siempre y solo con JSON válido."},
                {"role": "user", "content": prompt},
            ],
        }
        r = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    def _call_anthropic(self, prompt: str) -> str:
        api_key = os.environ["ANTHROPIC_API_KEY"]
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "max_tokens": 512,
            "temperature": self.temperature,
            "messages": [
                {"role": "user",
                 "content": f"{prompt}\n\nRespondé únicamente con un objeto JSON válido."},
            ],
        }
        r = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        r.raise_for_status()
        return r.json()["content"][0]["text"]

    def _call_ollama(self, prompt: str) -> str:
        host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        url = f"{host}/api/generate"
        payload = {
            "model": self.model,
            "prompt": (
                "Sos un agente de simulación que responde sólo con JSON válido.\n\n"
                f"{prompt}"
            ),
            "format": "json",
            "stream": False,
            "options": {"temperature": self.temperature},
            # Mantener el modelo cargado entre llamadas para no pagar el load cada vez
            "keep_alive": "10m",
        }
        r = requests.post(url, json=payload, timeout=self.timeout)
        r.raise_for_status()
        return r.json()["response"]

    # ----------------------------------------------------------------- warmup
    def warmup(self) -> float:
        """
        Pre-carga el modelo (Ollama / proveedores reales) con una llamada
        mínima para que la primera step no pague el cold-start.
        Devuelve segundos transcurridos.
        """
        import time
        t0 = time.perf_counter()
        if self.provider == "ollama":
            host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
            try:
                requests.post(
                    f"{host}/api/generate",
                    json={"model": self.model, "prompt": "", "keep_alive": "10m"},
                    timeout=self.timeout,
                )
            except Exception as e:
                print(f"  ! warmup falló: {e}")
        elif self.provider in ("openai", "anthropic"):
            try:
                self.complete_json('Devolvé {"ok": true}.', salt=0)
            except Exception as e:
                print(f"  ! warmup falló: {e}")
        return time.perf_counter() - t0


# --------------------------------------------------------------------------- #
def _safe_parse_json(text: str) -> dict[str, Any] | None:
    """Intenta parsear JSON; si viene con basura alrededor, busca el primer { ... }."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None
