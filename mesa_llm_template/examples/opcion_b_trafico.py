"""
Opción B · Tráfico urbano simulado (Mesa-LLM).

Cada commuter:
  - tiene una *persona* y una rutina habitual,
  - mira las condiciones del día (clima, tráfico, paro de transporte),
  - delega su decisión al LLM con `prompts/commuter.txt`,
  - elige modo de transporte y hora de salida.

Lo interesante es ver:
  - Cómo la elección **se desplaza** ante un *paro de subte*.
  - Cómo se concentra la salida cuando llueve.
  - La distribución de modos por persona.

Uso:
    python opcion_b_trafico.py --steps 10 --provider mock
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

import mesa

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from llm import LLMClient, StepProgress  # noqa: E402


# --------------------------------------------------------------------------- #
PERSONAS_TRAFICO = [
    "estudiante, sin auto, presupuesto ajustado",
    "ejecutiva, valora el tiempo más que el costo",
    "deportista, prefiere bici si el día acompaña",
    "padre con hijos, lleva auto siempre que puede",
    "jubilado, paciente, sin apuro",
    "freelance, horarios flexibles, prioriza ahorro",
    "ambientalista, evita el auto por principios",
    "comercial, viaja con muestras, necesita auto",
    "joven impaciente, odia esperar el subte",
    "minimalista, camina si se puede",
    "cómodo, auto siempre, no le importa el tráfico",
    "tech worker, trabaja remoto 3 días, va sólo 2",
]


# --------------------------------------------------------------------------- #
#  Generador de "el día"
# --------------------------------------------------------------------------- #
def generar_dia(rng) -> dict:
    return {
        "clima":      rng.choice(["soleado", "nublado", "lluvia"]),
        "trafico":    rng.choice(["fluido", "moderado", "congestionado"]),
        "transporte": rng.choices(
            ["normal", "demoras", "paro de subte"], weights=[7, 2, 1]
        )[0],
        "eventos":    rng.choice(["ninguno", "partido en River", "marcha en centro"]),
    }


# --------------------------------------------------------------------------- #
#  Agente
# --------------------------------------------------------------------------- #
def load_prompt() -> str:
    return (ROOT / "prompts" / "commuter.txt").read_text(encoding="utf-8")


def render_prompt(template: str, **kwargs) -> str:
    out = template
    for k, v in kwargs.items():
        out = out.replace("{" + k + "}", str(v))
    return out


class CommuterAgent(mesa.Agent):
    def __init__(self, model: "TrafficModel", persona: str, rutina: str):
        super().__init__(model)
        self.persona = persona
        self.rutina = rutina
        self.memoria: list[str] = []
        self.modo_history: list[str] = []
        self.hora_history: list[str] = []

    def step(self) -> None:
        prompt = render_prompt(
            self.model.prompt_template,
            persona=self.persona,
            rutina=self.rutina,
            clima=self.model.dia["clima"],
            trafico=self.model.dia["trafico"],
            transporte=self.model.dia["transporte"],
            eventos=self.model.dia["eventos"],
            memoria="; ".join(self.memoria[-3:]) or "(primer día)",
        )

        resp = self.model.llm.complete_json(
            prompt, salt=self.unique_id * 7 + self.model.steps_run
        )
        decision = resp.parsed or {"modo_transporte": "auto",
                                   "hora_salida": "08:00",
                                   "razon": "fallback"}

        modo = decision.get("modo_transporte", "auto")
        hora = decision.get("hora_salida", "08:00")
        self.modo_history.append(modo)
        self.hora_history.append(hora)
        self.memoria.append(
            f"día {self.model.steps_run+1}: {self.model.dia['clima']}, "
            f"{self.model.dia['transporte']} → fui en {modo} a las {hora}"
        )
        if self.model.progress is not None:
            self.model.progress.tick(
                self.model.steps_run + 1, self.unique_id, modo
            )


# --------------------------------------------------------------------------- #
#  Modelo
# --------------------------------------------------------------------------- #
class TrafficModel(mesa.Model):
    def __init__(
        self,
        n_agents: int = 12,
        provider: str = "auto",
        model_name: str | None = None,
        seed: int | None = 42,
        progress: StepProgress | None = None,
    ):
        super().__init__(rng=seed)
        self.steps_run = 0
        self.llm = LLMClient(provider=provider, model=model_name)
        self.prompt_template = load_prompt()
        self.progress = progress

        self.dia: dict = {}  # se rellena al inicio de cada step
        self.dias_log: list[dict] = []

        for i in range(n_agents):
            persona = PERSONAS_TRAFICO[i % len(PERSONAS_TRAFICO)]
            rutina = self.random.choice([
                "8:00 al centro en subte",
                "9:00 a oficina con auto",
                "8:30 a la facultad caminando",
                "horario flexible, después de las 9",
            ])
            agent = CommuterAgent(self, persona=persona, rutina=rutina)
            agent.unique_id = i

    def step(self) -> None:
        self.dia = generar_dia(self.random)
        self.dias_log.append(self.dia.copy())
        self.agents.shuffle_do("step")
        self.steps_run += 1


# --------------------------------------------------------------------------- #
#  Visualización
# --------------------------------------------------------------------------- #
MODOS = ["auto", "subte", "bici", "caminar"]
COLOR_MODO = {"auto": "#172186", "subte": "#FD8204",
              "bici": "#22a06b", "caminar": "#888888"}


def plot_results(model: TrafficModel, out_dir: Path) -> Path:
    fig = plt.figure(figsize=(13, 5.2))
    gs = fig.add_gridspec(1, 3, width_ratios=[1.2, 1.4, 1])
    ax_modo_dia  = fig.add_subplot(gs[0])
    ax_modo_pers = fig.add_subplot(gs[1])
    ax_horas     = fig.add_subplot(gs[2])

    # 1) Distribución de modos por step (barras apiladas)
    days = list(range(1, model.steps_run + 1))
    counts_per_day = {m: [] for m in MODOS}
    for d in range(model.steps_run):
        c = Counter(a.modo_history[d] for a in model.agents)
        for m in MODOS:
            counts_per_day[m].append(c.get(m, 0))

    bottom = np.zeros(len(days))
    for m in MODOS:
        vals = np.array(counts_per_day[m])
        ax_modo_dia.bar(days, vals, bottom=bottom, label=m, color=COLOR_MODO[m])
        bottom += vals

    # marcamos eventos especiales (paro)
    for i, d in enumerate(model.dias_log, start=1):
        if d["transporte"] == "paro de subte":
            ax_modo_dia.axvline(i, color="red", alpha=0.25, linewidth=8, ymax=1.0)

    ax_modo_dia.set_title("Modo de transporte por día\n(barra roja = paro de subte)")
    ax_modo_dia.set_xlabel("día"); ax_modo_dia.set_ylabel("commuters")
    ax_modo_dia.legend(fontsize=8, loc="upper right")

    # 2) Modo dominante por persona (heatmap)
    modos_pers: dict[str, Counter[str]] = defaultdict(Counter)
    for ag in model.agents:
        key = ag.persona.split(",")[0]
        for m in ag.modo_history:
            modos_pers[key][m] += 1

    keys = sorted(modos_pers.keys())
    matrix = np.array([[modos_pers[k].get(m, 0) for m in MODOS] for k in keys])
    im = ax_modo_pers.imshow(matrix, cmap="Oranges", aspect="auto")
    ax_modo_pers.set_xticks(range(len(MODOS)))
    ax_modo_pers.set_xticklabels(MODOS)
    ax_modo_pers.set_yticks(range(len(keys)))
    ax_modo_pers.set_yticklabels(keys, fontsize=8)
    ax_modo_pers.set_title("Frecuencia de modo por persona")
    for i, k in enumerate(keys):
        for j, m in enumerate(MODOS):
            v = matrix[i, j]
            if v:
                ax_modo_pers.text(j, i, str(v), ha="center", va="center",
                                  fontsize=8,
                                  color="white" if v > matrix.max()/2 else "#333")
    fig.colorbar(im, ax=ax_modo_pers, fraction=0.04)

    # 3) Distribución de hora de salida
    todas_horas = [h for ag in model.agents for h in ag.hora_history]
    horas_count = Counter(todas_horas)
    horas_sorted = sorted(horas_count.keys())
    ax_horas.bar(horas_sorted, [horas_count[h] for h in horas_sorted],
                 color="#172186", edgecolor="white")
    ax_horas.set_title("Hora de salida (todos)")
    ax_horas.set_ylabel("conteo")
    plt.setp(ax_horas.get_xticklabels(), rotation=45, ha="right", fontsize=8)

    fig.suptitle(
        f"Tráfico urbano · {len(model.agents)} commuters · provider={model.llm.provider}",
        fontsize=12,
    )
    fig.tight_layout()

    out_dir.mkdir(exist_ok=True)
    out_png = out_dir / "trafico_resultado.png"
    fig.savefig(out_png, dpi=120)
    plt.close(fig)
    return out_png


# --------------------------------------------------------------------------- #
#  CLI
# --------------------------------------------------------------------------- #
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--steps", type=int, default=10,
                        help="Cada step = un día simulado")
    parser.add_argument("--n-agents", type=int, default=12)
    parser.add_argument("--provider", default="auto",
                        choices=["auto", "openai", "anthropic", "ollama", "mock"])
    parser.add_argument("--model", default=None)
    parser.add_argument("--quiet", action="store_true",
                        help="No mostrar progress en vivo")
    args = parser.parse_args()

    progress = StepProgress(
        total_agents=args.n_agents, total_steps=args.steps,
        provider=args.provider, enabled=not args.quiet,
    )
    model = TrafficModel(
        n_agents=args.n_agents, provider=args.provider,
        model_name=args.model, progress=progress,
    )
    progress.provider = model.llm.provider
    print(f">> provider efectivo : {model.llm.provider} (model={model.llm.model})")
    print(f">> {len(model.agents)} commuters · {args.steps} días "
          f"· {len(model.agents) * args.steps} llamadas LLM")

    if model.llm.provider in ("ollama", "openai", "anthropic"):
        print(">> calentando modelo... (cold start de VRAM puede tardar 10-30s)")
        dt = model.llm.warmup()
        print(f">> modelo listo en {dt:.1f}s\n")
    else:
        print()

    for d in range(1, args.steps + 1):
        model.step()
        modos = Counter(a.modo_history[-1] for a in model.agents)
        progress.end_step(
            d, summary=f"{model.dia['clima']:>9} · {model.dia['transporte']:>15} · modos={dict(modos)}"
        )

    progress.finish()
    out_png = plot_results(model, ROOT / "examples" / "output")
    print(f">> {out_png}")


if __name__ == "__main__":
    main()
