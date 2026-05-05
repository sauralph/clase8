"""
Opción A · Consumidor en un mercado simulado (Mesa-LLM).

Cada agente:
  - tiene una *persona* (string libre) y un presupuesto inicial,
  - ve los productos disponibles, sus precios y un breve historial,
  - delega su decisión al LLM (real o mock) con `prompts/consumer.txt`,
  - actúa: comprar / esperar / negociar.

Métricas registradas:
  - Distribución de acciones por persona.
  - Gasto total por persona.
  - Volatilidad de precios.

Uso:
    python opcion_a_consumidor.py --steps 25 --provider mock
    python opcion_a_consumidor.py --provider openai --model gpt-4o-mini
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

import mesa

# Permitir `python examples/opcion_a_consumidor.py` desde cualquier dir
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from llm import LLMClient, StepProgress, RunRecorder  # noqa: E402


# --------------------------------------------------------------------------- #
#  Personas (edita esta lista para experimentar)
# --------------------------------------------------------------------------- #
# Personas con sesgo de acción EXPLÍCITO (clave para que el LLM no se ancle en
# "esperar" todo el tiempo).
PERSONAS = [
    "impulsivo: comprás casi siempre el primer producto que veas dentro de tu presupuesto",
    "impulsivo, fashion-victim: comprás cualquier producto trendy aunque ya tengas uno parecido",
    "ostentoso: te gusta gastar fuerte, comprás el producto más caro que puedas pagar",
    "gourmet: comprás el producto que percibís como de mayor calidad, sin importar precio",
    "negociador profesional: SIEMPRE intentás regatear primero; si baja el precio, comprás",
    "regateador casual: probás regatear 1 vez por turno antes de comprar",
    "racional: evaluás 1 turno y al siguiente comprás el de mejor precio/calidad",
    "ahorrativo: solo comprás cuando ves descuentos; sino, regateás",
    "ahorrativo extremo: solo comprás el producto más barato disponible",
    "escéptico: desconfiás, pero después de 3 turnos esperando comprás algo barato",
    "minimalista: comprás solo cosas baratas y necesarias (pan, café)",
    "joven impaciente: si no comprás algo en 2 turnos te frustrás y comprás cualquier cosa",
]


# Mapping persona-archetype → presupuesto típico, para que las decisiones
# tengan sentido (un ostentoso sin plata no puede ostentar).
def presupuesto_para(persona: str, rng) -> int:
    p = persona.lower()
    if "ostentoso" in p or "gourmet" in p:
        return rng.choice([1500, 3000, 9000])
    if "impulsivo" in p or "joven" in p:
        return rng.choice([300, 500, 1500])
    if "negociador" in p or "regateador" in p:
        return rng.choice([200, 500, 1500])
    if "racional" in p:
        return rng.choice([200, 500, 1500])
    if "minimalista" in p or "ahorrativo extremo" in p:
        return rng.choice([60, 90, 120])
    if "ahorrativo" in p or "escéptico" in p:
        return rng.choice([90, 200, 500])
    return rng.choice([200, 500, 1500])


# --------------------------------------------------------------------------- #
#  Eventos del turno (rompen el equilibrio "todos esperan")
# --------------------------------------------------------------------------- #
def generar_eventos(rng, prices: dict[int, int]) -> tuple[str, dict[int, float]]:
    """
    Devuelve (descripción legible, multiplicadores de precio por producto).
    Tipos:
      - promo : -25% en un producto random
      - escasez : producto a punto de agotarse (no afecta precio, signal de urgencia)
      - hype   : todos hablan de un producto (señal social)
      - nada
    """
    multipliers = {pid: 1.0 for pid in prices}
    kind = rng.choices(
        ["promo", "escasez", "hype", "nada"], weights=[3, 2, 2, 3]
    )[0]
    if kind == "nada":
        return "ningún evento especial hoy", multipliers
    pid = rng.choice(list(prices.keys()))
    nombre = PRODUCTS[pid]["nombre"]
    if kind == "promo":
        multipliers[pid] = 0.75
        return f"PROMO -25% en {nombre} (id={pid}) sólo este turno", multipliers
    if kind == "escasez":
        return f"ESCASEZ: quedan pocas unidades de {nombre} (id={pid})", multipliers
    if kind == "hype":
        return f"HYPE: todos están hablando de {nombre} (id={pid}) en redes", multipliers
    return "ningún evento especial hoy", multipliers


PRODUCTS = [
    {"id": 0, "nombre": "Pan integral",     "precio_base": 8},
    {"id": 1, "nombre": "Café de especialidad", "precio_base": 25},
    {"id": 2, "nombre": "Smartphone medio", "precio_base": 350},
    {"id": 3, "nombre": "Camisa Aurora",    "precio_base": 45},
    {"id": 4, "nombre": "Auto usado Polaris", "precio_base": 8000},
]


# --------------------------------------------------------------------------- #
#  Prompt loader
# --------------------------------------------------------------------------- #
def load_prompt() -> str:
    return (ROOT / "prompts" / "consumer.txt").read_text(encoding="utf-8")


def render_prompt(template: str, **kwargs: object) -> str:
    """Render seguro para `{var}` y `{{...}}` que sobreviven en el prompt."""
    out = template
    for k, v in kwargs.items():
        out = out.replace("{" + k + "}", str(v))
    return out


# --------------------------------------------------------------------------- #
#  Agente
# --------------------------------------------------------------------------- #
class ConsumerAgent(mesa.Agent):
    def __init__(self, model: "MarketModel", persona: str, presupuesto: int):
        super().__init__(model)
        self.persona = persona
        self.presupuesto = presupuesto
        self.gastado = 0
        self.memoria: list[str] = []
        self.acciones: list[str] = []  # historial propio
        self.turnos_esperando = 0       # racha de "esperar" consecutivas

    def step(self) -> None:
        productos_str = ", ".join(
            f"id={p['id']} {p['nombre']} (${self.model.prices_today[p['id']]})"
            for p in PRODUCTS
        )
        prompt = render_prompt(
            self.model.prompt_template,
            persona=self.persona,
            memoria="; ".join(self.memoria[-3:]) or "(sin memoria, primer turno)",
            productos=productos_str,
            presupuesto=self.presupuesto - self.gastado,
            eventos=self.model.evento_str,
            otros_agentes=self.model.peer_signal,
            turnos_esperando=self.turnos_esperando,
        )

        resp = self.model.llm.complete_json(prompt, salt=self.unique_id * 31 + self.model.steps_run)
        decision = resp.parsed or {"accion": "esperar", "producto_id": None,
                                   "razon": "no parsable", "estado_emocional": "neutro"}

        applied = self._apply(decision)

        if self.model.recorder is not None:
            self.model.recorder.record(
                step=self.model.steps_run + 1,
                agent_id=self.unique_id,
                persona=self.persona,
                prompt=prompt,
                raw_response=resp.text,
                parsed=resp.parsed,
                applied_action=applied,
                extra={
                    "presupuesto_disponible": self.presupuesto - self.gastado,
                    "turnos_esperando": self.turnos_esperando,
                },
            )
        if self.model.progress is not None:
            self.model.progress.tick(
                self.model.steps_run + 1,
                self.unique_id,
                applied,
            )

    # ------------------------------------------------------ aplicar acción
    def _apply(self, decision: dict) -> str:
        """Devuelve la acción efectivamente aplicada (puede diferir de decision.accion)."""
        accion = decision.get("accion", "esperar")
        pid = decision.get("producto_id")
        razon = decision.get("razon", "")

        # Pricing dinámico (toy): el precio se mueve un poco si hay compras
        if accion == "comprar" and isinstance(pid, int) and 0 <= pid < len(PRODUCTS):
            price = self.model.prices_today[pid]
            if price <= (self.presupuesto - self.gastado):
                self.gastado += price
                self.model.demand[pid] += 1
                self.acciones.append("comprar")
                self.memoria.append(f"compré {PRODUCTS[pid]['nombre']} a ${price}")
                self.turnos_esperando = 0
                return "comprar"
            else:
                accion = "esperar"
                razon = "(corregido) no me alcanza"
        if accion == "negociar" and isinstance(pid, int) and 0 <= pid < len(PRODUCTS):
            price = self.model.prices_today[pid]
            descuento = self.model.random.uniform(0.05, 0.15)
            new_price = int(price * (1 - descuento))
            self.model.proposed_discounts[pid].append(new_price)
            self.acciones.append("negociar")
            self.memoria.append(f"regateé {PRODUCTS[pid]['nombre']}, ofrecí ${new_price}")
            self.turnos_esperando = 0
            return "negociar"

        self.acciones.append("esperar")
        self.turnos_esperando += 1
        # Solo guardamos memoria de "esperar" cada 2 turnos para no saturar
        # con eventos triviales que anclen al LLM en seguir esperando.
        if self.turnos_esperando % 2 == 1:
            self.memoria.append(f"esperé porque {razon}")
        return "esperar"


# --------------------------------------------------------------------------- #
#  Modelo
# --------------------------------------------------------------------------- #
class MarketModel(mesa.Model):
    def __init__(
        self,
        n_agents: int = 12,
        provider: str = "auto",
        model_name: str | None = None,
        seed: int | None = 42,
        progress: StepProgress | None = None,
        recorder: RunRecorder | None = None,
    ):
        super().__init__(rng=seed)
        self.steps_run = 0
        self.prices = {p["id"]: p["precio_base"] for p in PRODUCTS}
        self.prices_today: dict[int, int] = dict(self.prices)  # con eventos aplicados
        self.demand: Counter[int] = Counter()
        self.proposed_discounts: dict[int, list[int]] = defaultdict(list)

        # Bump temperatura para LLMs reales: a 0.7 se estancan en "esperar".
        temp = 0.95 if provider in ("ollama", "openai", "anthropic", "auto") else 0.7
        self.llm = LLMClient(provider=provider, model=model_name, temperature=temp)
        self.prompt_template = load_prompt()
        self.progress = progress
        self.recorder = recorder

        # Estado de eventos / peer signal del turno actual
        self.evento_str = "primer turno, sin eventos"
        self.peer_signal = "(no hay turno previo)"
        # Metadata por step para el markdown de la corrida
        self.step_meta: dict[int, dict[str, str]] = {}

        for i in range(n_agents):
            persona = PERSONAS[i % len(PERSONAS)]
            presupuesto = presupuesto_para(persona, self.random)
            agent = ConsumerAgent(self, persona=persona, presupuesto=presupuesto)
            agent.unique_id = i

        self.history_prices: dict[int, list[float]] = {p["id"]: [] for p in PRODUCTS}

    def step(self) -> None:
        self.demand.clear()
        for d in self.proposed_discounts.values():
            d.clear()

        # Generar evento del turno y aplicar al precio del día
        self.evento_str, mults = generar_eventos(self.random, self.prices)
        self.prices_today = {pid: max(1, int(round(self.prices[pid] * m)))
                             for pid, m in mults.items()}

        # Peer signal: qué hicieron los agentes el turno pasado
        if self.steps_run > 0:
            last_actions = Counter(a.acciones[-1] for a in self.agents if a.acciones)
            top_buys = Counter()
            for a in self.agents:
                if a.acciones and a.acciones[-1] == "comprar" and a.memoria:
                    last_mem = a.memoria[-1]
                    if last_mem.startswith("compré "):
                        top_buys[last_mem.split("compré ")[1].split(" a $")[0]] += 1
            buy_str = ", ".join(f"{n}×{c}" for n, c in top_buys.most_common(3)) or "ninguno compró"
            self.peer_signal = (
                f"{dict(last_actions)} · top compras: {buy_str}"
            )
        else:
            self.peer_signal = "(no hay turno previo)"

        # Guardamos meta del step ANTES de ejecutar (para el reporte)
        self.step_meta[self.steps_run + 1] = {
            "evento": self.evento_str,
            "peer": self.peer_signal,
        }

        self.agents.shuffle_do("step")
        self.steps_run += 1
        self._update_prices()
        for pid, price in self.prices.items():
            self.history_prices[pid].append(price)

    def _update_prices(self) -> None:
        """Pricing toy: si hay alta demanda sube; si hubo regateos baja un poco."""
        for pid, base in [(p["id"], p["precio_base"]) for p in PRODUCTS]:
            d = self.demand.get(pid, 0)
            disc = self.proposed_discounts.get(pid, [])
            change = 0.04 * d - 0.02 * len(disc)
            new = self.prices[pid] * (1 + change)
            # mean reversion suave hacia el precio base
            new = 0.7 * new + 0.3 * base
            self.prices[pid] = max(1, int(round(new)))


# --------------------------------------------------------------------------- #
#  Visualización
# --------------------------------------------------------------------------- #
def _persona_key(persona: str) -> str:
    """Etiqueta corta y legible para el plot (≤ 18 chars)."""
    head = persona.split(":")[0].split(",")[0].strip()
    return head[:18]


def plot_results(model: MarketModel, out_dir: Path) -> Path:
    actions_by_persona: dict[str, Counter[str]] = defaultdict(Counter)
    spend_by_persona: dict[str, int] = defaultdict(int)
    for ag in model.agents:
        key = _persona_key(ag.persona)
        for act in ag.acciones:
            actions_by_persona[key][act] += 1
        spend_by_persona[key] += ag.gastado

    fig = plt.figure(figsize=(13, 5.2))
    gs = fig.add_gridspec(1, 3, width_ratios=[1.3, 1, 1])
    ax_actions = fig.add_subplot(gs[0])
    ax_spend = fig.add_subplot(gs[1])
    ax_prices = fig.add_subplot(gs[2])

    keys = sorted(actions_by_persona.keys())
    actions = ["comprar", "negociar", "esperar"]
    colors = {"comprar": "#172186", "negociar": "#FD8204", "esperar": "#cccccc"}
    bottom = np.zeros(len(keys))
    for act in actions:
        vals = np.array([actions_by_persona[k].get(act, 0) for k in keys])
        ax_actions.barh(keys, vals, left=bottom, label=act, color=colors[act])
        bottom += vals
    ax_actions.set_title("Acciones por tipo de persona")
    ax_actions.set_xlabel("nº de acciones")
    ax_actions.legend(loc="lower right")
    ax_actions.invert_yaxis()

    keys2 = sorted(spend_by_persona.keys(), key=lambda k: spend_by_persona[k], reverse=True)
    vals2 = [spend_by_persona[k] for k in keys2]
    ax_spend.barh(keys2, vals2, color="#172186")
    ax_spend.set_title("Gasto total por persona")
    ax_spend.set_xlabel("$")
    ax_spend.invert_yaxis()

    for pid in model.history_prices:
        ax_prices.plot(model.history_prices[pid], label=PRODUCTS[pid]["nombre"][:14])
    ax_prices.set_title("Volatilidad de precios")
    ax_prices.set_xlabel("step")
    ax_prices.set_ylabel("$")
    ax_prices.set_yscale("log")
    ax_prices.legend(fontsize=8)

    fig.suptitle(
        f"Mercado · {len(model.agents)} agentes · provider={model.llm.provider}"
        + (f" ({model.llm.model})" if model.llm.model else ""),
        fontsize=12,
    )
    fig.tight_layout()

    out_dir.mkdir(exist_ok=True)
    out_png = out_dir / "consumidor_resultado.png"
    fig.savefig(out_png, dpi=120)
    plt.close(fig)
    return out_png


# --------------------------------------------------------------------------- #
#  CLI
# --------------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--steps", type=int, default=15)
    parser.add_argument("--n-agents", type=int, default=12)
    parser.add_argument("--provider", default="auto",
                        choices=["auto", "openai", "anthropic", "ollama", "mock"])
    parser.add_argument("--model", default=None,
                        help="Override del modelo (ej: gpt-4o-mini)")
    parser.add_argument("--quiet", action="store_true",
                        help="No mostrar progress en vivo")
    parser.add_argument("--no-record", action="store_true",
                        help="No volcar JSONL/markdown a output/")
    args = parser.parse_args()

    out_dir = ROOT / "examples" / "output"
    print(f">> provider seleccionado : {args.provider}")
    progress = StepProgress(
        total_agents=args.n_agents, total_steps=args.steps,
        provider=args.provider, enabled=not args.quiet,
    )
    recorder = RunRecorder(
        out_dir=out_dir, label="consumer",
        provider=args.provider, model=args.model,
        n_agents=args.n_agents, total_steps=args.steps,
        enabled=not args.no_record,
    )
    model = MarketModel(
        n_agents=args.n_agents, provider=args.provider,
        model_name=args.model, progress=progress, recorder=recorder,
    )
    progress.provider = model.llm.provider
    if recorder.enabled:
        recorder.provider = model.llm.provider
        recorder.model = model.llm.model
    print(f">> provider efectivo     : {model.llm.provider} (model={model.llm.model})")
    print(f">> {len(model.agents)} agentes · {args.steps} steps "
          f"· {len(model.agents) * args.steps} llamadas LLM totales")

    if model.llm.provider in ("ollama", "openai", "anthropic"):
        print(">> calentando modelo... (cold start de VRAM puede tardar 10-30s)")
        dt = model.llm.warmup()
        print(f">> modelo listo en {dt:.1f}s\n")
    else:
        print()

    for t in range(1, args.steps + 1):
        model.step()
        actions_now = Counter(a.acciones[-1] for a in model.agents if a.acciones)
        progress.end_step(t, summary=f"acciones={dict(actions_now)}")

    progress.finish()
    out_png = plot_results(model, out_dir)
    print(f">> {out_png}")

    if recorder.enabled:
        precios_str = "Precios finales: " + ", ".join(
            f"{PRODUCTS[pid]['nombre']}=${p}" for pid, p in model.prices.items()
        )
        md_path = recorder.write_markdown(
            step_meta=model.step_meta, extra_summary=precios_str,
        )
        recorder.close()
        print(f">> {recorder.path_jsonl}")
        print(f">> {md_path}")


if __name__ == "__main__":
    main()
