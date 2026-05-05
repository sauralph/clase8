"""
Sugarscape (Epstein & Axtell, 1996) — implementado en Mesa 3.5+.

El mundo es una grilla con dos "picos" de azúcar. Cada agente tiene:
  - vision        : cuántas celdas ve a la redonda
  - metabolism    : cuánta azúcar consume por step
  - sugar         : reserva acumulada (su "riqueza")

En cada step un agente:
  1. Mira las celdas vacías dentro de su vision.
  2. Se mueve a la que tenga MÁS azúcar (desempate por cercanía).
  3. Cosecha toda el azúcar de esa celda.
  4. Paga su metabolismo. Si su reserva queda en 0, muere.
La azúcar de cada celda regenera a `growback_rate` hasta `capacity`.

Lo que emerge:
  - Aglomeración de agentes en los picos.
  - Migración cuando un pico se "vacía" mientras crece el otro.
  - Distribución de riqueza tipo Pareto (Gini alto) sin haberla programado.

Uso:
    python sugarscape.py [--no-gif] [--steps 100] [--n-agents 250]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.colors import LinearSegmentedColormap

import mesa


# --------------------------------------------------------------------------- #
#  Paisaje de azúcar
# --------------------------------------------------------------------------- #
def make_sugar_landscape(width: int, height: int) -> np.ndarray:
    """Capacidad de azúcar por celda — dos picos opuestos, niveles 0-4."""
    capacity = np.zeros((height, width), dtype=int)
    centers = [(0.25 * width, 0.25 * height), (0.75 * width, 0.75 * height)]
    radius_step = 0.15 * max(width, height)

    for cy in range(height):
        for cx in range(width):
            d = min(np.hypot(cx - c[0], cy - c[1]) for c in centers)
            level = max(0, 4 - int(d // radius_step))
            capacity[cy, cx] = level
    return capacity


# --------------------------------------------------------------------------- #
#  Agente
# --------------------------------------------------------------------------- #
class SugarAgent(mesa.Agent):
    """Un buscador de azúcar con vision, metabolism y reserva."""

    def __init__(
        self,
        model: "SugarscapeModel",
        vision: int,
        metabolism: int,
        sugar: int,
    ):
        super().__init__(model)
        self.vision = vision
        self.metabolism = metabolism
        self.sugar = sugar  # reserva / riqueza acumulada

    def step(self) -> None:
        self._move_and_eat()
        self.sugar -= self.metabolism
        if self.sugar <= 0:
            self.model.deaths += 1
            self.model.grid.remove_agent(self)
            self.remove()  # baja del AgentSet

    def _move_and_eat(self) -> None:
        # Celdas dentro de la vision (Chebyshev / King's move)
        candidates = self.model.grid.get_neighborhood(
            self.pos, moore=True, include_center=True, radius=self.vision
        )

        # Filtramos las que están vacías (excepto la propia)
        free = [
            c for c in candidates
            if c == self.pos or self.model.grid.is_cell_empty(c)
        ]

        # Tomamos la(s) de mayor azúcar; desempate por cercanía
        best_sugar = max(self.model.sugar[y, x] for x, y in free)
        cx, cy = self.pos
        best = [
            (x, y) for (x, y) in free
            if self.model.sugar[y, x] == best_sugar
        ]
        best.sort(key=lambda p: abs(p[0] - cx) + abs(p[1] - cy))
        # Si hay varias a la misma distancia, una al azar entre ellas
        d_min = abs(best[0][0] - cx) + abs(best[0][1] - cy)
        ties = [p for p in best if abs(p[0] - cx) + abs(p[1] - cy) == d_min]
        new_pos = self.random.choice(ties)

        if new_pos != self.pos:
            self.model.grid.move_agent(self, new_pos)

        # Cosechar
        x, y = new_pos
        self.sugar += int(self.model.sugar[y, x])
        self.model.sugar[y, x] = 0


# --------------------------------------------------------------------------- #
#  Modelo
# --------------------------------------------------------------------------- #
class SugarscapeModel(mesa.Model):
    def __init__(
        self,
        width: int = 50,
        height: int = 50,
        n_agents: int = 250,
        growback_rate: int = 1,
        seed: int | None = 42,
    ):
        super().__init__(rng=seed)
        self.growback_rate = growback_rate
        self.deaths = 0

        self.grid = mesa.space.SingleGrid(width, height, torus=False)
        self.capacity = make_sugar_landscape(width, height)
        self.sugar = self.capacity.copy().astype(int)

        # Crear agentes en celdas vacías al azar
        empty = list(self.grid.empties)
        self.random.shuffle(empty)
        for pos in empty[:n_agents]:
            agent = SugarAgent(
                self,
                vision=self.random.randint(1, 6),
                metabolism=self.random.randint(1, 4),
                sugar=self.random.randint(5, 25),
            )
            self.grid.place_agent(agent, pos)

        self.datacollector = mesa.DataCollector(
            model_reporters={
                "alive": lambda m: len(m.agents),
                "deaths": lambda m: m.deaths,
                "gini": lambda m: gini([a.sugar for a in m.agents]),
                "total_sugar": lambda m: int(m.sugar.sum()),
            }
        )
        self.datacollector.collect(self)

    def step(self) -> None:
        # 1) Crece el azúcar
        self.sugar = np.minimum(self.sugar + self.growback_rate, self.capacity)
        # 2) Cada agente decide y come
        self.agents.shuffle_do("step")
        # 3) Métricas
        self.datacollector.collect(self)


def gini(values: list[int]) -> float:
    """Coeficiente de Gini sobre una lista de riquezas."""
    if not values:
        return 0.0
    arr = np.sort(np.asarray(values, dtype=float))
    if arr.sum() == 0:
        return 0.0
    n = len(arr)
    idx = np.arange(1, n + 1)
    return float((2 * np.sum(idx * arr)) / (n * arr.sum()) - (n + 1) / n)


# --------------------------------------------------------------------------- #
#  Ejecución + visualización
# --------------------------------------------------------------------------- #
def grid_snapshot(model: SugarscapeModel) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Devuelve (sugar_grid, agent_xs, agent_ys)."""
    xs = np.array([a.pos[0] for a in model.agents])
    ys = np.array([a.pos[1] for a in model.agents])
    return model.sugar.copy(), xs, ys


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--steps", type=int, default=100)
    parser.add_argument("--width", type=int, default=50)
    parser.add_argument("--height", type=int, default=50)
    parser.add_argument("--n-agents", type=int, default=250)
    parser.add_argument("--growback-rate", type=int, default=1)
    parser.add_argument("--no-gif", action="store_true")
    args = parser.parse_args()

    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(exist_ok=True)

    model = SugarscapeModel(
        width=args.width,
        height=args.height,
        n_agents=args.n_agents,
        growback_rate=args.growback_rate,
    )

    snapshots = [grid_snapshot(model)]
    print(f"step   0   alive={len(model.agents):3d}   deaths={model.deaths:3d}   "
          f"gini={gini([a.sugar for a in model.agents]):.3f}")
    for t in range(1, args.steps + 1):
        model.step()
        snapshots.append(grid_snapshot(model))
        if t % 10 == 0 or t == 1:
            wealths = [a.sugar for a in model.agents]
            print(f"step {t:3d}   alive={len(model.agents):3d}   "
                  f"deaths={model.deaths:3d}   gini={gini(wealths):.3f}")

    df = model.datacollector.get_model_vars_dataframe()

    # ---- figura final --------------------------------------------------------
    fig = plt.figure(figsize=(13, 5.2))
    gs = fig.add_gridspec(1, 3, width_ratios=[1, 1, 1.1])
    ax_grid = fig.add_subplot(gs[0])
    ax_metrics = fig.add_subplot(gs[1])
    ax_hist = fig.add_subplot(gs[2])

    sugar_cmap = LinearSegmentedColormap.from_list(
        "sugar", ["#ffffff", "#ffe4b5", "#FD8204"]
    )

    sugar_grid, xs, ys = snapshots[-1]
    ax_grid.imshow(sugar_grid, cmap=sugar_cmap, vmin=0, vmax=4, origin="lower")
    ax_grid.scatter(xs, ys, s=14, c="#172186", edgecolors="white", linewidths=0.3)
    ax_grid.set_title(f"Estado final · t={args.steps} · alive={len(model.agents)}")
    ax_grid.set_xticks([]); ax_grid.set_yticks([])

    ax_metrics.plot(df.index, df["alive"], color="#172186", label="vivos")
    ax_metrics.plot(df.index, df["deaths"], color="#FD8204", label="muertos acum.")
    ax_metrics.set_xlabel("step")
    ax_metrics.set_ylabel("agentes")
    ax_metrics.set_title("Población")
    ax_metrics.grid(alpha=0.3); ax_metrics.legend()

    ax_hist.plot(df.index, df["gini"], color="#FD8204", linewidth=2)
    ax_hist.set_xlabel("step")
    ax_hist.set_ylabel("Gini de la riqueza")
    ax_hist.set_ylim(0, 1)
    ax_hist.set_title("Desigualdad emergente")
    ax_hist.grid(alpha=0.3)

    fig.tight_layout()
    out_png = out_dir / "sugarscape_final.png"
    fig.savefig(out_png, dpi=120)
    plt.close(fig)
    print(f"\n>> {out_png}")

    # ---- gif animado ---------------------------------------------------------
    if not args.no_gif:
        fig_anim, ax_anim = plt.subplots(figsize=(5, 5))
        sugar0, xs0, ys0 = snapshots[0]
        im = ax_anim.imshow(sugar0, cmap=sugar_cmap, vmin=0, vmax=4, origin="lower")
        scat = ax_anim.scatter(
            xs0, ys0, s=14, c="#172186", edgecolors="white", linewidths=0.3
        )
        title = ax_anim.set_title("Sugarscape · step 0")
        ax_anim.set_xticks([]); ax_anim.set_yticks([])

        def update(frame: int):
            sugar, xs, ys = snapshots[frame]
            im.set_data(sugar)
            scat.set_offsets(np.c_[xs, ys])
            title.set_text(f"Sugarscape · step {frame}")
            return im, scat, title

        anim = FuncAnimation(
            fig_anim, update, frames=len(snapshots), interval=100, blit=False
        )
        out_gif = out_dir / "sugarscape.gif"
        anim.save(out_gif, writer=PillowWriter(fps=10))
        plt.close(fig_anim)
        print(f">> {out_gif}")


if __name__ == "__main__":
    main()
