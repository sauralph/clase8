"""
Modelo de Boids (Reynolds, 1987) — implementado en Mesa 3.5+.

Tres reglas locales que cada boid aplica mirando solo a sus vecinos:

  1. Cohesión   — moverse hacia el centro de masa de los vecinos.
  2. Separación — alejarse de los que están demasiado cerca.
  3. Alineación — copiar la dirección promedio de los vecinos.

Con esas tres reglas y *sin líder*, emergen bandadas, vórtices y *splits*.
Es uno de los ejemplos canónicos de comportamiento emergente en ABM.

Uso:
    python boids.py [--no-gif] [--steps 200] [--n-boids 80]
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
class Boid(mesa.Agent):
    """Un boid con posición y velocidad en R^2."""

    def __init__(
        self,
        model: "BoidModel",
        velocity: np.ndarray,
        vision: float = 5.0,
        separation_dist: float = 1.5,
        max_speed: float = 1.5,
    ):
        super().__init__(model)
        self.velocity = np.asarray(velocity, dtype=float)
        self.vision = vision
        self.separation_dist = separation_dist
        self.max_speed = max_speed

    def step(self) -> None:
        neighbors = self.model.space.get_neighbors(
            self.pos, self.vision, include_center=False
        )

        if neighbors:
            cohesion   = self._cohesion(neighbors)
            separation = self._separation(neighbors)
            alignment  = self._alignment(neighbors)

            self.velocity += (
                self.model.cohesion_w   * cohesion
                + self.model.separation_w * separation
                + self.model.alignment_w  * alignment
            )

        # limitar la velocidad para que no se disparen
        speed = np.linalg.norm(self.velocity)
        if speed > self.max_speed:
            self.velocity *= self.max_speed / speed

        new_pos = np.asarray(self.pos) + self.velocity
        self.model.space.move_agent(self, tuple(new_pos))

    # ------------------------------------------------------------- reglas
    def _cohesion(self, neighbors: list["Boid"]) -> np.ndarray:
        center = np.mean([n.pos for n in neighbors], axis=0)
        return (center - np.asarray(self.pos)) * 0.05

    def _separation(self, neighbors: list["Boid"]) -> np.ndarray:
        push = np.zeros(2)
        for n in neighbors:
            offset = np.asarray(self.pos) - np.asarray(n.pos)
            d = np.linalg.norm(offset)
            if 0 < d < self.separation_dist:
                push += offset / (d * d)
        return push

    def _alignment(self, neighbors: list["Boid"]) -> np.ndarray:
        avg_v = np.mean([n.velocity for n in neighbors], axis=0)
        return (avg_v - self.velocity) * 0.10


# --------------------------------------------------------------------------- #
#  Modelo
# --------------------------------------------------------------------------- #
class BoidModel(mesa.Model):
    def __init__(
        self,
        n_boids: int = 80,
        width: float = 60.0,
        height: float = 60.0,
        cohesion_w: float = 1.0,
        separation_w: float = 1.0,
        alignment_w: float = 1.0,
        seed: int | None = 42,
    ):
        super().__init__(rng=seed)
        self.cohesion_w = cohesion_w
        self.separation_w = separation_w
        self.alignment_w = alignment_w

        self.space = mesa.space.ContinuousSpace(width, height, torus=True)

        for _ in range(n_boids):
            x = self.random.uniform(0, width)
            y = self.random.uniform(0, height)
            angle = self.random.uniform(0, 2 * np.pi)
            v = np.array([np.cos(angle), np.sin(angle)])
            boid = Boid(self, velocity=v)
            self.space.place_agent(boid, (x, y))

    def step(self) -> None:
        self.agents.shuffle_do("step")


# --------------------------------------------------------------------------- #
#  Ejecución + visualización
# --------------------------------------------------------------------------- #
def snapshot(model: BoidModel) -> tuple[np.ndarray, np.ndarray]:
    pos = np.array([a.pos for a in model.agents])
    vel = np.array([a.velocity for a in model.agents])
    return pos, vel


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--steps", type=int, default=200)
    parser.add_argument("--n-boids", type=int, default=80)
    parser.add_argument("--width", type=float, default=60.0)
    parser.add_argument("--height", type=float, default=60.0)
    parser.add_argument("--no-gif", action="store_true")
    args = parser.parse_args()

    out_dir = Path(__file__).parent / "output"
    out_dir.mkdir(exist_ok=True)

    model = BoidModel(
        n_boids=args.n_boids, width=args.width, height=args.height
    )

    snapshots = [snapshot(model)]
    print(f"step   0   boids={args.n_boids}")
    for t in range(1, args.steps + 1):
        model.step()
        snapshots.append(snapshot(model))
        if t % 50 == 0 or t == 1:
            pos, vel = snapshots[-1]
            mean_speed = np.mean(np.linalg.norm(vel, axis=1))
            heading = np.linalg.norm(np.mean(vel, axis=0))
            print(f"step {t:3d}   speed={mean_speed:.2f}   |mean v|={heading:.2f}")

    # ---- figura final --------------------------------------------------------
    fig, (ax_traj, ax_final) = plt.subplots(1, 2, figsize=(12, 5))

    # 1) trayectorias (últimos N pasos)
    # Por el torus, cuando un boid cruza el borde aparece un "salto" enorme;
    # lo enmascaramos como NaN para que matplotlib no dibuje esa línea.
    tail = min(60, len(snapshots) - 1)
    for i in range(args.n_boids):
        xs = np.array([snapshots[t][0][i, 0] for t in range(len(snapshots) - tail, len(snapshots))], float)
        ys = np.array([snapshots[t][0][i, 1] for t in range(len(snapshots) - tail, len(snapshots))], float)
        dx = np.abs(np.diff(xs))
        dy = np.abs(np.diff(ys))
        jump = (dx > args.width / 2) | (dy > args.height / 2)
        xs[1:][jump] = np.nan
        ys[1:][jump] = np.nan
        ax_traj.plot(xs, ys, color="#172186", alpha=0.25, linewidth=0.7)
    ax_traj.set_xlim(0, args.width)
    ax_traj.set_ylim(0, args.height)
    ax_traj.set_aspect("equal")
    ax_traj.set_title(f"Trayectorias (últimos {tail} steps)")
    ax_traj.set_xticks([])
    ax_traj.set_yticks([])
    ax_traj.set_facecolor("#fafafa")

    # 2) estado final con flechas
    pos, vel = snapshots[-1]
    ax_final.quiver(
        pos[:, 0], pos[:, 1],
        vel[:, 0], vel[:, 1],
        color="#FD8204", scale=25, width=0.005,
    )
    ax_final.set_xlim(0, args.width)
    ax_final.set_ylim(0, args.height)
    ax_final.set_aspect("equal")
    ax_final.set_title(f"Estado final · t={args.steps}")
    ax_final.set_xticks([])
    ax_final.set_yticks([])
    ax_final.set_facecolor("#fafafa")

    fig.tight_layout()
    out_png = out_dir / "boids_final.png"
    fig.savefig(out_png, dpi=120)
    plt.close(fig)
    print(f"\n>> {out_png}")

    # ---- gif animado ---------------------------------------------------------
    if not args.no_gif:
        fig_anim, ax_anim = plt.subplots(figsize=(5, 5))
        pos0, vel0 = snapshots[0]
        quiv = ax_anim.quiver(
            pos0[:, 0], pos0[:, 1],
            vel0[:, 0], vel0[:, 1],
            color="#FD8204", scale=25, width=0.005,
        )
        title = ax_anim.set_title("Boids · step 0")
        ax_anim.set_xlim(0, args.width)
        ax_anim.set_ylim(0, args.height)
        ax_anim.set_aspect("equal")
        ax_anim.set_xticks([])
        ax_anim.set_yticks([])
        ax_anim.set_facecolor("#fafafa")

        def update(frame: int):
            pos, vel = snapshots[frame]
            quiv.set_offsets(pos)
            quiv.set_UVC(vel[:, 0], vel[:, 1])
            title.set_text(f"Boids · step {frame}")
            return quiv, title

        # Para que pese poco: muestreo 1 de cada 2 frames
        frames = list(range(0, len(snapshots), 2))
        anim = FuncAnimation(
            fig_anim, update, frames=frames, interval=80, blit=False
        )
        out_gif = out_dir / "boids.gif"
        anim.save(out_gif, writer=PillowWriter(fps=15))
        plt.close(fig_anim)
        print(f">> {out_gif}")


if __name__ == "__main__":
    main()
