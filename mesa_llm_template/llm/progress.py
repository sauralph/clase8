"""
Progress feedback en vivo para simulaciones LLM-driven.

Pensado para casos donde cada llamada al modelo tarda 1-3 s
(Ollama / API real) y la simulación completa puede llevar minutos.
Funciona con stdout standard (sin dependencias extra) y respeta
el ancho de la terminal.
"""

from __future__ import annotations

import shutil
import sys
import time


class StepProgress:
    """
    Muestra una línea sobreescribible con:
      step k/N · agent i/M · last=accion · X.X call/s · eta Y s
    y al cerrar cada step imprime un resumen estable.
    """

    def __init__(
        self,
        total_agents: int,
        total_steps: int,
        provider: str = "?",
        enabled: bool = True,
    ):
        self.total_agents = total_agents
        self.total_steps = total_steps
        self.provider = provider
        self.enabled = enabled and sys.stdout.isatty()
        self.t_start = time.perf_counter()
        self.calls = 0
        self._last_print = 0.0

    # --------------------------------------------------------------- helpers
    @staticmethod
    def _term_width() -> int:
        try:
            return shutil.get_terminal_size((100, 20)).columns
        except OSError:
            return 100

    def _format_line(self, step: int, agent_idx: int, last_action: str) -> str:
        elapsed = max(time.perf_counter() - self.t_start, 1e-3)
        rate = self.calls / elapsed
        total = self.total_agents * self.total_steps
        eta = (total - self.calls) / max(rate, 1e-3)
        return (
            f"  step {step:>2}/{self.total_steps} · "
            f"agent {agent_idx + 1:>2}/{self.total_agents} · "
            f"last={last_action:<9} · "
            f"{rate:5.1f} call/s · "
            f"eta {eta:5.0f}s"
        )

    # ------------------------------------------------------------------ API
    def tick(self, step: int, agent_idx: int, last_action: str) -> None:
        """Llamar una vez por cada decisión LLM completada."""
        self.calls += 1
        if not self.enabled:
            return
        # Throttle: no spammear stdout más de ~20 veces por segundo
        now = time.perf_counter()
        if now - self._last_print < 0.05 and self.calls < self.total_agents * self.total_steps:
            return
        self._last_print = now
        line = self._format_line(step, agent_idx, last_action)
        line = line[: self._term_width() - 1]
        sys.stdout.write("\r\x1b[2K" + line)
        sys.stdout.flush()

    def end_step(self, step: int, summary: str) -> None:
        """Llamar al terminar un step. Imprime una línea estable y baja."""
        if self.enabled:
            sys.stdout.write("\r\x1b[2K")
            sys.stdout.flush()
        elapsed = time.perf_counter() - self.t_start
        rate = self.calls / max(elapsed, 1e-3)
        print(
            f"  step {step:>2}/{self.total_steps} done · "
            f"{self.calls} calls · {rate:.1f} call/s · "
            f"{summary}"
        )

    def finish(self) -> None:
        elapsed = time.perf_counter() - self.t_start
        rate = self.calls / max(elapsed, 1e-3)
        print(
            f"\n  -- {self.calls} llamadas en {elapsed:.1f}s "
            f"({rate:.1f} call/s) · provider={self.provider} --"
        )
