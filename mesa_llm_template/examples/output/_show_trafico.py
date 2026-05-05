"""Imprime persona / modo_transporte / razon del JSONL del recorder."""
import json
import sys
from pathlib import Path

DEFAULT = "trafico_20260505_130619.jsonl"
path = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent / DEFAULT)

records = []
for line in path.read_text(encoding="utf-8").splitlines():
    r = json.loads(line)
    if r.get("_meta"):
        continue
    parsed = r.get("parsed") or {}
    records.append({
        "step":    r["step"],
        "ag":      r["agent_id"],
        "persona": r["persona"].split(",")[0],
        "modo":    parsed.get("modo_transporte", "?"),
        "razon":   (parsed.get("razon") or "").strip(),
    })

records.sort(key=lambda x: (x["step"], x["ag"]))
pw = max(len(r["persona"]) for r in records)
mw = max(len(r["modo"]) for r in records)

current = None
for r in records:
    if r["step"] != current:
        current = r["step"]
        print(f"\n--- step {current} ---")
    print(f"  ag {r['ag']:>2}  {r['persona']:<{pw}}  {r['modo']:<{mw}}  | {r['razon']}")
