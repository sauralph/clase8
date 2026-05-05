"""
LLM "fake" — basado en reglas, devuelve JSON respetando el schema.

Usado como fallback cuando no hay API keys ni Ollama corriendo, así la
actividad práctica de la clase corre 100% offline.

No pretende ser inteligente; sí ser:
- Determinístico dada una semilla.
- Coherente con la persona del agente (lee palabras clave del prompt).
- Suficiente para que la simulación produzca curvas razonables.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from typing import Any


# -- diccionarios de "actitudes" por keyword en la persona ------------------- #

_KEYWORDS_BUY = (
    "impulsivo", "fashion", "gourmet", "hedonista", "compulsivo", "ostentoso"
)
_KEYWORDS_SAVE = (
    "ahorrativo", "minimalista", "racional", "frugal", "esceptico", "escéptico"
)
_KEYWORDS_NEGOTIATE = (
    "negociador", "regateador", "experto", "profesional", "comerciante"
)

_EMOTIONS_HAPPY    = ("entusiasmado", "satisfecho", "esperanzado", "alegre")
_EMOTIONS_NEUTRAL  = ("neutro", "expectante", "atento", "calmo")
_EMOTIONS_NEGATIVE = ("escéptico", "molesto", "preocupado", "frustrado")


# --------------------------------------------------------------------------- #
def _seed_from_prompt(prompt: str, salt: int = 0) -> int:
    """Convierte el prompt + salt en un seed determinístico."""
    h = hashlib.sha1(f"{salt}|{prompt}".encode("utf-8")).hexdigest()
    return int(h[:8], 16)


def _detect_persona_bias(prompt: str) -> str:
    p = prompt.lower()
    if any(k in p for k in _KEYWORDS_BUY):
        return "buy"
    if any(k in p for k in _KEYWORDS_NEGOTIATE):
        return "negotiate"
    if any(k in p for k in _KEYWORDS_SAVE):
        return "save"
    return "neutral"


def _extract_field(prompt: str, field: str) -> str | None:
    """Busca 'Campo: valor' en el prompt para usar contexto."""
    m = re.search(
        rf"^\s*{re.escape(field)}\s*[:=]\s*(.+)$",
        prompt, re.IGNORECASE | re.MULTILINE,
    )
    return m.group(1).strip() if m else None


# --------------------------------------------------------------------------- #
def fake_consumer(prompt: str, salt: int = 0) -> dict[str, Any]:
    """Respuesta para el agente consumidor (Opción A)."""
    rng = random.Random(_seed_from_prompt(prompt, salt))
    bias = _detect_persona_bias(prompt)

    presupuesto_raw = _extract_field(prompt, "Tu presupuesto") or ""
    m_pres = re.search(r"\$?\s*(\d+)", presupuesto_raw)
    presupuesto = int(m_pres.group(1)) if m_pres else 100

    productos_raw = _extract_field(prompt, "Productos disponibles") or ""
    ids = [int(x) for x in re.findall(r"\bid\s*=\s*(\d+)", productos_raw)]
    if not ids:
        ids = list(range(5))

    # Decisión de acción según el bias y un poco de azar
    if bias == "buy":
        accion = rng.choices(["comprar", "esperar", "negociar"],
                             weights=[7, 2, 1])[0]
        emocion_pool = _EMOTIONS_HAPPY
    elif bias == "save":
        accion = rng.choices(["comprar", "esperar", "negociar"],
                             weights=[2, 6, 2])[0]
        emocion_pool = _EMOTIONS_NEUTRAL
    elif bias == "negotiate":
        accion = rng.choices(["comprar", "esperar", "negociar"],
                             weights=[3, 2, 5])[0]
        emocion_pool = _EMOTIONS_NEUTRAL + _EMOTIONS_HAPPY
    else:
        accion = rng.choices(["comprar", "esperar", "negociar"],
                             weights=[4, 4, 2])[0]
        emocion_pool = _EMOTIONS_NEUTRAL

    # Ajuste por presupuesto bajo
    if presupuesto < 30 and accion == "comprar":
        accion = rng.choice(["esperar", "negociar"])
        emocion_pool = _EMOTIONS_NEGATIVE

    producto_id = rng.choice(ids) if accion in ("comprar", "negociar") else None

    razones = {
        "comprar":  ["el precio es razonable", "vi que otro lo recomendó",
                     "lo necesito ahora", "no quiero perder la oportunidad"],
        "esperar":  ["espero que baje el precio", "no estoy convencido",
                     "necesito pensarlo", "no es prioridad hoy"],
        "negociar": ["creo que está caro", "puedo conseguir mejor precio",
                     "quiero un descuento", "tengo otra oferta similar"],
    }
    razon = rng.choice(razones[accion])

    return {
        "accion": accion,
        "producto_id": producto_id,
        "razon": razon,
        "estado_emocional": rng.choice(emocion_pool),
    }


def fake_commuter(prompt: str, salt: int = 0) -> dict[str, Any]:
    """Respuesta para el agente commuter (Opción B · tráfico)."""
    rng = random.Random(_seed_from_prompt(prompt, salt))
    p = prompt.lower()

    # Eventos que afectan la decisión
    raining   = "lluvia" in p or "rain" in p
    transit   = "paro" in p or "huelga" in p
    crowded   = "congestionado" in p or "tráfico" in p

    if raining and not transit:
        modo = rng.choices(["auto", "subte", "bici", "caminar"],
                           weights=[5, 4, 0, 1])[0]
    elif transit:
        modo = rng.choices(["auto", "bici", "caminar"], weights=[4, 4, 2])[0]
    elif crowded:
        modo = rng.choices(["bici", "subte", "caminar", "auto"],
                           weights=[5, 4, 2, 1])[0]
    else:
        modo = rng.choices(["auto", "subte", "bici", "caminar"],
                           weights=[3, 4, 2, 1])[0]

    salida = rng.choice(["07:30", "08:00", "08:15", "08:30", "09:00"])

    razones = [
        "más rápido en este escenario",
        "lo uso por costumbre",
        "es más barato",
        "me gusta caminar un poco",
        "evito el tráfico",
    ]
    return {
        "modo_transporte": modo,
        "hora_salida": salida,
        "razon": rng.choice(razones),
    }


# --------------------------------------------------------------------------- #
def fake_default(prompt: str, salt: int = 0) -> dict[str, Any]:
    """Respuesta genérica si no detectamos el dominio."""
    rng = random.Random(_seed_from_prompt(prompt, salt))
    return {
        "accion": rng.choice(["esperar", "responder", "consultar"]),
        "razon": "respuesta genérica del mock",
    }


def respond(prompt: str, schema: dict[str, Any] | None = None,
            salt: int = 0) -> str:
    """
    Heurística simple: detecta el dominio por keywords del prompt y devuelve
    JSON serializado al estilo de un LLM real.
    """
    p = prompt.lower()
    if any(k in p for k in ("consumidor", "mercado", "producto", "presupuesto")):
        result = fake_consumer(prompt, salt=salt)
    elif any(k in p for k in ("commuter", "tránsito", "transporte", "ruta")):
        result = fake_commuter(prompt, salt=salt)
    else:
        result = fake_default(prompt, salt=salt)
    return json.dumps(result, ensure_ascii=False)
