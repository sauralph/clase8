"""
Modelo SIR en agentes — implementado en Mesa 3.5+.

Cada agente vive en una grilla, está en uno de tres estados (S/I/R) y
camina al azar. Si un Susceptible cae junto a un Infectado, se contagia
con probabilidad `infection_prob`. Después de `recovery_steps` pasos
infectado, el agente se recupera (R) y queda inmune.

A diferencia del SIR clásico (ODEs), acá la dinámica es **espacial**
y heterogénea: los brotes locales empiezan, se expanden y mueren.

Uso:
    python sir.py [--no-gif] [--steps 80] [--n-agents 200] [--n-initial-infected 3]
"""

from __future__ import annotations

import argparse
from enum import IntEnum
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FuncAnimation, PillowWriter

import mesa


# --------------------------------------------------------------------------- #
#  Estados
# --------------------------------------------------------------------------- #
class State(IntEnum):
    SUSCEPTIBLE = 0
    INFECTED = 1
    RECOVERED = 2


COLOR = {
    State.SUSCEPTIBLE: "#888888",
    State.INFECTED:    "#FD8204",
    State.RECOVERED:   "#172186",
}


# --------------------------------------------------------------------------- #
#  Agente
# --------------------------------------------------------------------------- #
class Person(mesa.Agent):
    """Una persona que se mueve, se contagia y eventualmente se recupera."""

    def __init__(self, model: "SIRModel", state: State = State.SUSCEPTIBLE):
        super().__init__(model)
        self.state = state
        self.infected_for = 0  # pasos que lleva infectado

    def step(self) -> None:
        self._move()
        self._update_health()

    def _move(self) -> None:
        """Camino aleatorio: a una celda vecina (incluyendo la actual)."""
        choices = self.model.grid.get_neighborhood(
            self.pos, moore=True, include_center=True
        )
        new_pos = self.random.choice(choices)
        self.model.grid.move_agent(self, new_pos)

    def _update_health(self) -> None:
        if self.state == State.INFECTED:
            self.infected_for += 1
            if self.infected_for >= self.model.recovery_steps:
                self.state = State.RECOVERED
            return

        if self.state == State.SUSCEPTIBLE:
            cellmates = self.model.grid.get_cell_list_contents([self.pos])
            n_infected_here = sum(
                1 for a in cellmates if a is not self and a.state == State.INFECTED
            )
            # cada infectado en mi celda me intenta contagiar
            if n_infected_here and self.random.random() < (
                1 - (1 - self.model.infection_prob) ** n_infected_here
            ):
                self.state = State.INFECTED


# --------------------------------------------------------------------------- #
#  Modelo
# --------------------------------------------------------------------------- #
class SIRModel(mesa.Model):
    def __init__(
        self,
        width: int = 30,
        height: int = 30,
        n_agents: int = 200,
        n_initial_infected: int = 3,
        infection_prob: float = 0.20,
        recovery_steps: int = 14,
        seed: int | None = 42,
    ):
        super().__init__(rng=seed)
        self.infection_prob = infection_prob
        self.recovery_steps = recovery_steps

        self.grid = mesa.space.MultiGrid(width, height, torus=True)

        for i in range(n_agents):
            initial = (
                State.INFECTED if i < n_initial_infected else State.SUSCEPTIBLE
            )
            agent = Person(self, state=initial)
            x = self.random.randrange(width)
            y = self.random.randrange(height)
            self.grid.place_agent(agent, (x, y))

        self.datacollector = mesa.DataCollector(
            model_reporters={
                "S": lambda m: m._count(State.SUSCEPTIBLE),
                "I": lambda m: m._count(State.INFECTED),
                "R": lambda m: m._count(State.RECOVERED),
            }
        )
        self.datacollector.collect(self)

    def _count(self, state: State) -> int:
        return sum(1 for a in self.agents if a.state == state)

    def step(self) -> None:
        self.agents.shuffle_do("step")
        self.datacollector.collect(self)


# --------------------------------------------------------------------------- #
#  Ejecución + visualización
# --------------------------------------------------------------------------- #
def grid_snapshot(model: SIRModel) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Devuelve (xs, ys, colors) con un punto por agente."""
    xs, ys, colors = [], [], []
    for agent in model.agents:
        x, y = agent.pos
        xs.append(x + 0.5)
        ys.append(y + 0.5)
        colors.append(COLOR[agent.state])
    return np.array(xs), np.array(ys), np.array(colors)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--steps", type=int, default=80)
    parser.add_argument("--width", type=int, default=25)
    parser.add_argument("--height", type=int, default=25)
    parser.add_argument("--n-agents", type=int, default=400)
    parser.add_argument("--n-initial-infected", type=int, default=3)
    parser.add_argument("--infection-prob", type=float, default=0.35)
    parser.add_argument("--recovery-steps", type=int, default=14)
    parser.add_argument("--no-gif", action="store_true")
    args = parser.parse_args()

    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(exist_ok=True)

    model = SIRModel(
        width=args.width,
        height=args.height,
        n_agents=args.n_agents,
        n_initial_infected=args.n_initial_infected,
        infection_prob=args.infection_prob,
        recovery_steps=args.recovery_steps,
    )

    snapshots = [grid_snapshot(model)]
    print(f"step  0  S={model._count(State.SUSCEPTIBLE):3d}  "
          f"I={model._count(State.INFECTED):3d}  "
          f"R={model._count(State.RECOVERED):3d}")
    for t in range(1, args.steps + 1):
        model.step()
        snapshots.append(grid_snapshot(model))
        if t % 10 == 0 or t == 1:
            print(f"step {t:2d}  S={model._count(State.SUSCEPTIBLE):3d}  "
                  f"I={model._count(State.INFECTED):3d}  "
                  f"R={model._count(State.RECOVERED):3d}")

    df = model.datacollector.get_model_vars_dataframe()

    # ---- figura final --------------------------------------------------------
    fig, (ax_grid, ax_curve) = plt.subplots(
        1, 2, figsize=(12, 5), gridspec_kw={"width_ratios": [1, 1.2]}
    )

    xs, ys, colors = snapshots[-1]
    ax_grid.scatter(xs, ys, c=colors, s=40, edgecolors="white", linewidths=0.4)
    ax_grid.set_xlim(0, args.width)
    ax_grid.set_ylim(0, args.height)
    ax_grid.set_aspect("equal")
    ax_grid.set_title(f"Estado final · t={args.steps}")
    ax_grid.set_xticks([])
    ax_grid.set_yticks([])
    ax_grid.set_facecolor("#f5f5f5")

    ax_curve.plot(df.index, df["S"], color=COLOR[State.SUSCEPTIBLE],
                  label="Susceptibles", linewidth=2)
    ax_curve.plot(df.index, df["I"], color=COLOR[State.INFECTED],
                  label="Infectados", linewidth=2)
    ax_curve.plot(df.index, df["R"], color=COLOR[State.RECOVERED],
                  label="Recuperados", linewidth=2)
    ax_curve.set_xlabel("step")
    ax_curve.set_ylabel("agentes")
    ax_curve.set_title(
        f"SIR · p={args.infection_prob:.2f}, recovery={args.recovery_steps}"
    )
    ax_curve.legend()
    ax_curve.grid(alpha=0.3)

    fig.tight_layout()
    out_png = out_dir / "sir_final.png"
    fig.savefig(out_png, dpi=120)
    plt.close(fig)
    print(f"\n>> {out_png}")

    # ---- gif animado ---------------------------------------------------------
    if not args.no_gif:
        fig_anim, ax_anim = plt.subplots(figsize=(5, 5))
        scat = ax_anim.scatter(
            snapshots[0][0], snapshots[0][1],
            c=snapshots[0][2], s=40, edgecolors="white", linewidths=0.4,
        )
        title = ax_anim.set_title("SIR · step 0")
        ax_anim.set_xlim(0, args.width)
        ax_anim.set_ylim(0, args.height)
        ax_anim.set_aspect("equal")
        ax_anim.set_xticks([])
        ax_anim.set_yticks([])
        ax_anim.set_facecolor("#f5f5f5")

        def update(frame: int):
            xs, ys, colors = snapshots[frame]
            scat.set_offsets(np.c_[xs, ys])
            scat.set_color(colors)
            title.set_text(f"SIR · step {frame}")
            return scat, title

        anim = FuncAnimation(
            fig_anim, update, frames=len(snapshots), interval=120, blit=False
        )
        out_gif = out_dir / "sir.gif"
        anim.save(out_gif, writer=PillowWriter(fps=10))
        plt.close(fig_anim)
        print(f">> {out_gif}")


if __name__ == "__main__":
    main()
