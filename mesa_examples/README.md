# Ejemplos sencillos de ABM con Mesa

Cuatro modelos clásicos para acompañar la sección **§2 — ABM tradicionales** de
la presentación `llm_abm.md`. Cada script es **autocontenido** (~80–200 líneas),
se ejecuta solo, y produce una figura `*.png` y un GIF animado en `output/`.

| Script           | Modelo                                | Espacio          | Lo que muestra                                                |
| ---------------- | ------------------------------------- | ---------------- | ------------------------------------------------------------- |
| `schelling.py`   | Segregación de Schelling (1971)       | grilla discreta  | Tolerancia individual → segregación global                    |
| `sir.py`         | Epidemia SIR en agentes               | grilla discreta  | Curvas S/I/R emergentes desde reglas locales                  |
| `boids.py`       | Flocking de Reynolds (Boids, 1987)    | espacio continuo | Bandadas sin líder a partir de 3 reglas                       |
| `sugarscape.py`  | Sugarscape (Epstein & Axtell, 1996)   | grilla discreta  | Migración a recursos + desigualdad (Gini) emergentes          |

Todos están escritos contra **Mesa 3.5+**. Si tenés Mesa 2.x, no van a correr
sin retoques (la API cambió bastante).

## Instalación

```powershell
# Desde el venv del repo
pip install -r mesa_examples/requirements.txt
```

## Cómo correrlos

Desde el directorio `clase8/`:

```powershell
python mesa_examples/schelling.py
python mesa_examples/sir.py
python mesa_examples/boids.py
python mesa_examples/sugarscape.py
```

Cada uno imprime métricas en la consola y deja en `mesa_examples/output/`:

- `<modelo>_final.png` — estado final + curvas de métricas.
- `<modelo>.gif` — animación del modelo a lo largo de los pasos.

Para correr **sin generar el GIF** (más rápido), pasá `--no-gif`:

```powershell
python mesa_examples/schelling.py --no-gif
```

## Filosofía bottom-up

Los tres ejemplos comparten la estructura mínima de un ABM:

```text
  ┌──────────┐         ┌──────────────┐
  │  Agent   │ × N  ──►│   Model      │
  │  step()  │         │   step()     │── tick del reloj
  └──────────┘         │   space      │── donde viven
                       │   datacollector
                       └──────────────┘
```

- Cada **agente** tiene estado y una regla `step()` local.
- El **modelo** los mete en un espacio y avanza el reloj.
- El comportamiento global **emerge** — no se programa explícitamente.

Esa es exactamente la limitación que los **LLM-ABM** vienen a romper:
agentes con razonamiento, memoria y lenguaje en lugar de reglas rígidas.
