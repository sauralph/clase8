"""
Modelo de Segregación de Schelling (1971) — implementado en Mesa 3.5+.

Cada agente vive en una grilla, pertenece a un grupo (0 o 1), y tiene una
tolerancia mínima `homophily`: si la fracción de vecinos del *mismo grupo*
cae por debajo de ese umbral, el agente se muda a una celda vacía cualquiera.

Lo interesante: con tolerancias *moderadas* (~30 %), nadie pide segregación
y sin embargo emerge segregación masiva.

Uso:
    python schelling.py [--no-gif] [--steps 60] [--width 30] [--height 30]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FuncAnimation, PillowWriter

import mesa


# --------------------------------------------------------------------------- #
#  Agente
# --------------------------------------------------------------------------- #
class SchellingAgent(mesa.Agent):
    """Un residente con un grupo y una tolerancia mínima."""

    def __init__(self, model: "SchellingModel", group: int):
        super().__init__(model)
        self.group = group

    def step(self) -> None:
        """Si tengo pocos vecinos del mismo grupo, me mudo."""
        neighbors = self.model.grid.get_neighbors(
            self.pos, moore=True, include_center=False
        )
        if not neighbors:
            return

        same = sum(1 for n in neighbors if n.group == self.group)
        share_same = same / len(neighbors)

        if share_same < self.model.homophily:
            self.model.grid.move_to_empty(self)
            self.model.unhappy_count += 1


# --------------------------------------------------------------------------- #
#  Modelo
# --------------------------------------------------------------------------- #
class SchellingModel(mesa.Model):
    """Mundo de Schelling: grilla con dos grupos y celdas vacías."""

    def __init__(
        self,
        width: int = 30,
        height: int = 30,
        density: float = 0.85,
        minority_share: float = 0.4,
        homophily: float = 0.30,
        seed: int | None = 42,
    ):
        super().__init__(rng=seed)
        self.homophily = homophily
        self.unhappy_count = 0

        self.grid = mesa.space.SingleGrid(width, height, torus=True)

        for cell in self.grid.coord_iter():
            _, pos = cell
            if self.random.random() < density:
                group = 0 if self.random.random() < minority_share else 1
                agent = SchellingAgent(self, group=group)
                self.grid.place_agent(agent, pos)

        self.datacollector = mesa.DataCollector(
            model_reporters={
                "unhappy": lambda m: m.unhappy_count,
                "happy": lambda m: len(m.agents) - m.unhappy_count,
            }
        )
        self.datacollector.collect(self)

    def step(self) -> None:
        self.unhappy_count = 0
        self.agents.shuffle_do("step")
        self.datacollector.collect(self)


# --------------------------------------------------------------------------- #
#  Ejecución + visualización
# --------------------------------------------------------------------------- #
def grid_snapshot(model: SchellingModel) -> np.ndarray:
    """Devuelve un array (H, W) con -1=vacío, 0=grupo0, 1=grupo1."""
    arr = np.full((model.grid.height, model.grid.width), -1, dtype=int)
    for agent in model.agents:
        x, y = agent.pos
        arr[y, x] = agent.group
    return arr


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--steps", type=int, default=60)
    parser.add_argument("--width", type=int, default=30)
    parser.add_argument("--height", type=int, default=30)
    parser.add_argument("--homophily", type=float, default=0.30)
    parser.add_argument("--no-gif", action="store_true")
    args = parser.parse_args()

    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(exist_ok=True)

    model = SchellingModel(
        width=args.width,
        height=args.height,
        homophily=args.homophily,
    )

    snapshots = [grid_snapshot(model)]
    print(f"step  0  unhappy={model.unhappy_count:4d}")
    for t in range(1, args.steps + 1):
        model.step()
        snapshots.append(grid_snapshot(model))
        if t % 10 == 0 or t == 1:
            print(f"step {t:2d}  unhappy={model.unhappy_count:4d}")

    df = model.datacollector.get_model_vars_dataframe()

    # ---- figura final --------------------------------------------------------
    fig, (ax_grid, ax_metrics) = plt.subplots(
        1, 2, figsize=(12, 5), gridspec_kw={"width_ratios": [1, 1.2]}
    )

    cmap = plt.matplotlib.colors.ListedColormap(["#f0f0f0", "#172186", "#FD8204"])
    ax_grid.imshow(snapshots[-1] + 1, cmap=cmap, vmin=0, vmax=2)
    ax_grid.set_title(f"Estado final · t={args.steps}")
    ax_grid.set_xticks([])
    ax_grid.set_yticks([])

    ax_metrics.plot(df.index, df["happy"], color="#172186", label="contentos")
    ax_metrics.plot(df.index, df["unhappy"], color="#FD8204", label="se mudaron")
    ax_metrics.set_xlabel("step")
    ax_metrics.set_ylabel("agentes")
    ax_metrics.set_title(f"Schelling · homophily = {args.homophily:.2f}")
    ax_metrics.legend()
    ax_metrics.grid(alpha=0.3)

    fig.tight_layout()
    out_png = out_dir / "schelling_final.png"
    fig.savefig(out_png, dpi=120)
    plt.close(fig)
    print(f"\n>> {out_png}")

    # ---- gif animado ---------------------------------------------------------
    if not args.no_gif:
        fig_anim, ax_anim = plt.subplots(figsize=(5, 5))
        im = ax_anim.imshow(snapshots[0] + 1, cmap=cmap, vmin=0, vmax=2)
        title = ax_anim.set_title("Schelling · step 0")
        ax_anim.set_xticks([])
        ax_anim.set_yticks([])

        def update(frame: int):
            im.set_data(snapshots[frame] + 1)
            title.set_text(f"Schelling · step {frame}")
            return im, title

        anim = FuncAnimation(
            fig_anim, update, frames=len(snapshots), interval=120, blit=False
        )
        out_gif = out_dir / "schelling.gif"
        anim.save(out_gif, writer=PillowWriter(fps=8))
        plt.close(fig_anim)
        print(f">> {out_gif}")


if __name__ == "__main__":
    main()
