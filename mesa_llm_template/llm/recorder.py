"""
Recorder de corridas LLM-driven.

Escribe DOS archivos por simulación, ambos en `examples/output/`:

  1. `<label>_<timestamp>.jsonl`   — un registro por llamada al LLM
       (prompt completo, raw response, parsed JSON, qué se aplicó).
       Pensado para post-mortem / análisis con jq, pandas, etc.

  2. `<label>_<timestamp>.md`      — resumen humanamente legible:
       una tabla por step con persona, acción, razón, estado emocional.
       Útil para el debrief de la clase y para detectar *anclajes* del LLM.

Uso típico:

    rec = RunRecorder(out_dir, label="consumer", provider="ollama",
                      model="llama3.2:3b", n_agents=12, total_steps=15)
    # ... durante la simulación ...
    rec.record(step=t, agent_id=a.unique_id, ...)
    # ... al final ...
    rec.write_markdown(extra_meta={"prices_final": ...})
"""

from __future__ import annotations

import json
import os
import re
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


def _now_tag() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _short(text: str | None, n: int = 80) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", str(text)).strip()
    return text if len(text) <= n else text[: n - 1] + "…"


class RunRecorder:
    def __init__(
        self,
        out_dir: Path,
        label: str,
        provider: str,
        model: str | None,
        n_agents: int,
        total_steps: int,
        enabled: bool = True,
    ):
        self.enabled = enabled
        self.label = label
        self.provider = provider
        self.model = model
        self.n_agents = n_agents
        self.total_steps = total_steps
        self.t_start_iso = datetime.now().isoformat(timespec="seconds")
        self.t_start = time.perf_counter()

        out_dir.mkdir(exist_ok=True, parents=True)
        tag = _now_tag()
        self.path_jsonl = out_dir / f"{label}_{tag}.jsonl"
        self.path_md = out_dir / f"{label}_{tag}.md"

        self.records: list[dict[str, Any]] = []
        if self.enabled:
            self._jsonl_fh = self.path_jsonl.open("w", encoding="utf-8")
            self._write_header()
        else:
            self._jsonl_fh = None

    # -------------------------------------------------------------- header
    def _write_header(self) -> None:
        meta = {
            "_meta": True,
            "label": self.label,
            "provider": self.provider,
            "model": self.model,
            "n_agents": self.n_agents,
            "total_steps": self.total_steps,
            "started_at": self.t_start_iso,
        }
        self._jsonl_fh.write(json.dumps(meta, ensure_ascii=False) + "\n")
        self._jsonl_fh.flush()

    # -------------------------------------------------------------- record
    def record(
        self,
        step: int,
        agent_id: int,
        persona: str,
        prompt: str,
        raw_response: str,
        parsed: dict | None,
        applied_action: str,
        extra: dict | None = None,
    ) -> None:
        rec = {
            "step": step,
            "agent_id": agent_id,
            "persona": persona,
            "prompt": prompt,
            "raw_response": raw_response,
            "parsed": parsed,
            "applied_action": applied_action,
        }
        if extra:
            rec.update(extra)
        self.records.append(rec)
        if self._jsonl_fh:
            self._jsonl_fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            self._jsonl_fh.flush()

    # -------------------------------------------------------------- close
    def close(self) -> None:
        if self._jsonl_fh:
            self._jsonl_fh.close()
            self._jsonl_fh = None

    # ---------------------------------------------------------- markdown
    def write_markdown(
        self,
        step_meta: dict[int, dict[str, str]] | None = None,
        extra_summary: str | None = None,
    ) -> Path:
        """
        step_meta : dict {step_number: {"evento": "...", "peer": "..."}}
                    (opcional, agrega contexto al header de cada step)
        extra_summary : texto libre que va antes de las tablas (ej. precios)
        """
        if not self.enabled:
            return self.path_md
        elapsed = time.perf_counter() - self.t_start
        rate = len(self.records) / max(elapsed, 1e-3)
        by_step: dict[int, list[dict]] = defaultdict(list)
        for r in self.records:
            by_step[r["step"]].append(r)

        lines: list[str] = []
        lines.append(f"# Run `{self.label}` · {self.t_start_iso}")
        lines.append("")
        lines.append(f"- provider : `{self.provider}` · modelo `{self.model}`")
        lines.append(f"- agentes  : {self.n_agents}")
        lines.append(f"- steps    : {self.total_steps}")
        lines.append(f"- llamadas : {len(self.records)}")
        lines.append(f"- duración : {elapsed:.1f}s ({rate:.2f} call/s)")
        lines.append(f"- jsonl    : `{self.path_jsonl.name}`")
        lines.append("")
        if extra_summary:
            lines.append("## Resumen")
            lines.append("")
            lines.append(extra_summary)
            lines.append("")

        for step in sorted(by_step.keys()):
            lines.append(f"## Step {step}")
            lines.append("")
            if step_meta and step in step_meta:
                m = step_meta[step]
                if m.get("evento"):
                    lines.append(f"- **evento** : {m['evento']}")
                if m.get("peer"):
                    lines.append(f"- **peers**  : {m['peer']}")
                lines.append("")
            lines.append("| ag | persona | acción | razón | estado | aplicada |")
            lines.append("| --- | --- | --- | --- | --- | --- |")
            for r in sorted(by_step[step], key=lambda x: x["agent_id"]):
                p = r.get("parsed") or {}
                aplicada = "ok" if r["applied_action"] == p.get("accion") else f"→ {r['applied_action']}"
                lines.append(
                    f"| {r['agent_id']} "
                    f"| {_short(r['persona'], 28)} "
                    f"| {p.get('accion', '?')} "
                    f"| {_short(p.get('razon'), 60)} "
                    f"| {_short(p.get('estado_emocional'), 18)} "
                    f"| {aplicada} |"
                )
            lines.append("")

        self.path_md.write_text("\n".join(lines), encoding="utf-8")
        return self.path_md

    # ------------------------------------------------------------------- ctx
    def __enter__(self) -> "RunRecorder":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
