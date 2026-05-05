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

from llm import LLMClient  # noqa: E402


# --------------------------------------------------------------------------- #
#  Personas (edita esta lista para experimentar)
# --------------------------------------------------------------------------- #
PERSONAS = [
    "ahorrativo, busca siempre el precio más bajo",
    "ahorrativo, calcula todo antes de gastar",
    "impulsivo, compra por antojo si le entra por los ojos",
    "impulsivo, fashion-victim, sigue las modas",
    "escéptico, desconfía del marketing y los descuentos",
    "escéptico, lee reviews antes de cada compra",
    "racional, evalúa relación precio-calidad fríamente",
    "racional, pragmático, sin lealtad de marca",
    "negociador, profesional del regateo",
    "gourmet, valora calidad por sobre precio",
    "minimalista, compra solo lo estrictamente necesario",
    "ostentoso, le gusta mostrar lo que tiene",
    "fiel a la marca, repite compras de Aurora siempre",
    "joven, primera compra grande, sin experiencia",
    "experimentado, lleva años comprando en este mercado",
]


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

    def step(self) -> None:
        productos_str = ", ".join(
            f"id={p['id']} {p['nombre']} (${self.model.prices[p['id']]})"
            for p in PRODUCTS
        )
        prompt = render_prompt(
            self.model.prompt_template,
            persona=self.persona,
            memoria="; ".join(self.memoria[-3:]) or "(sin memoria)",
            estado=f"step {self.model.steps_run}, oferta del día",
            productos=productos_str,
            presupuesto=self.presupuesto - self.gastado,
        )

        resp = self.model.llm.complete_json(prompt, salt=self.unique_id * 31 + self.model.steps_run)
        decision = resp.parsed or {"accion": "esperar", "producto_id": None,
                                   "razon": "no parsable", "estado_emocional": "neutro"}

        self._apply(decision)

    # ------------------------------------------------------ aplicar acción
    def _apply(self, decision: dict) -> None:
        accion = decision.get("accion", "esperar")
        pid = decision.get("producto_id")
        razon = decision.get("razon", "")
        emo = decision.get("estado_emocional", "neutro")

        # Pricing dinámico (toy): el precio se mueve un poco si hay compras
        if accion == "comprar" and isinstance(pid, int) and 0 <= pid < len(PRODUCTS):
            price = self.model.prices[pid]
            if price <= (self.presupuesto - self.gastado):
                self.gastado += price
                self.model.demand[pid] += 1
                self.acciones.append("comprar")
                self.memoria.append(f"compré {PRODUCTS[pid]['nombre']} a ${price} ({razon})")
                return
            else:
                accion = "esperar"  # no puede pagar
                razon = "(corregido) no me alcanza"
        if accion == "negociar" and isinstance(pid, int) and 0 <= pid < len(PRODUCTS):
            price = self.model.prices[pid]
            descuento = self.model.random.uniform(0.05, 0.15)
            new_price = int(price * (1 - descuento))
            self.model.proposed_discounts[pid].append(new_price)
            self.acciones.append("negociar")
            self.memoria.append(f"intenté regatear {PRODUCTS[pid]['nombre']} a ${new_price}")
            return

        self.acciones.append("esperar")
        self.memoria.append(f"esperé ({razon}, {emo})")


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
    ):
        super().__init__(rng=seed)
        self.steps_run = 0
        self.prices = {p["id"]: p["precio_base"] for p in PRODUCTS}
        self.demand: Counter[int] = Counter()
        self.proposed_discounts: dict[int, list[int]] = defaultdict(list)

        self.llm = LLMClient(provider=provider, model=model_name)
        self.prompt_template = load_prompt()

        for i in range(n_agents):
            persona = PERSONAS[i % len(PERSONAS)]
            presupuesto = self.random.choice([60, 90, 120, 200, 500, 1500, 9000])
            agent = ConsumerAgent(self, persona=persona, presupuesto=presupuesto)
            # asignamos un unique_id estable para el salt del mock
            agent.unique_id = i

        self.history_prices: dict[int, list[float]] = {p["id"]: [] for p in PRODUCTS}

    def step(self) -> None:
        self.demand.clear()
        for d in self.proposed_discounts.values():
            d.clear()

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
def plot_results(model: MarketModel, out_dir: Path) -> Path:
    actions_by_persona: dict[str, Counter[str]] = defaultdict(Counter)
    spend_by_persona: dict[str, int] = defaultdict(int)
    for ag in model.agents:
        key = ag.persona.split(",")[0]  # primera palabra clave
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
    args = parser.parse_args()

    print(f">> provider seleccionado : {args.provider}")
    model = MarketModel(
        n_agents=args.n_agents, provider=args.provider, model_name=args.model
    )
    print(f">> provider efectivo     : {model.llm.provider} (model={model.llm.model})")
    print(f">> {len(model.agents)} agentes, {args.steps} steps\n")

    for t in range(1, args.steps + 1):
        model.step()
        if t == 1 or t % 5 == 0 or t == args.steps:
            actions_now = Counter(a.acciones[-1] for a in model.agents if a.acciones)
            print(f"step {t:2d}  acciones={dict(actions_now)}  prices={model.prices}")

    out_png = plot_results(model, ROOT / "examples" / "output")
    print(f"\n>> {out_png}")


if __name__ == "__main__":
    main()
