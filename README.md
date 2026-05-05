# Clase 8 · LLMs en Agent-Based Models

**Materia**: Simulación en Ciencia de Datos · **Universidad Austral · 2026**

Esta clase explora cómo combinar **modelos de lenguaje grandes (LLMs)** con
**modelos basados en agentes (ABM)**: agentes que en lugar de seguir reglas
rígidas pueden *razonar, recordar y conversar*.

Sesión de **180 minutos** divididos en 8 secciones, con una práctica
guiada de **35 minutos** al final.

## Contenido de la carpeta

```
clase8/
├── README.md                    # este archivo
├── llm_abm.md                   # slides MARP (1164 líneas, 8 secciones)
├── llm_abm.pdf                  # render PDF (gitignored)
├── llm_abm.pptx                 # render PPTX (gitignored)
├── assets/                      # imágenes corporativas para las slides
│   ├── austral_bg.jpg
│   └── austral_divider.jpg
├── mesa_examples/               # 4 ABM clásicos en Mesa 3.5 (Python puro)
│   ├── schelling.py
│   ├── sir.py
│   ├── boids.py
│   ├── sugarscape.py
│   └── README.md
└── mesa_llm_template/           # plantilla LLM + Mesa para la práctica
    ├── llm/                     # cliente unificado (OpenAI/Anthropic/Ollama/Mock)
    ├── prompts/                 # 5 templates de prompts editables
    ├── examples/                # opcion_a (consumidor), opcion_b (tráfico)
    ├── data/brand_opinions.csv  # dataset sintético
    ├── notebook_colab.ipynb     # listo para subir a Google Colab
    └── README.md
```

## Las slides

Las 1164 líneas de `llm_abm.md` están escritas en
[MARP](https://marp.app/) con un tema custom basado en el branding de
Austral (azul `#172186`, naranja `#FD8204`, fuente Century Gothic).

### Secciones

| # | Sección | Duración | Formato |
| - | --- | --- | --- |
| 1 | Introducción y *hook* | 15 min | exposición + video |
| 2 | Fundamentos de ABM tradicionales | 25 min | teoría + demo |
| 3 | LLMs: arquitectura y capacidades | 20 min | teoría + ejemplos |
| 4 | Integración de LLMs en ABM | 35 min | teoría + demo en vivo |
| 5 | Aplicaciones y casos de estudio | 30 min | ejemplos reales |
| 6 | Desafíos, limitaciones y evaluación | 20 min | discusión |
| 7 | **Actividad práctica guiada** | **35 min** | grupo / individual |
| 8 | Futuro, tendencias y conclusión | 15 min | cierre + Q&A |

### Renderizar a PDF / PPTX

Sin Node.js local, usar Docker:

```powershell
# PDF
docker run --rm --init -v "${PWD}:/home/marp/app/" marpteam/marp-cli `
    llm_abm.md --pdf --allow-local-files

# PPTX
docker run --rm --init -v "${PWD}:/home/marp/app/" marpteam/marp-cli `
    llm_abm.md --pptx --allow-local-files

# Servidor de preview en vivo
docker run --rm --init -p 8080:8080 -v "${PWD}:/home/marp/app/" marpteam/marp-cli `
    -s --allow-local-files .
```

## Las dos demos en código

### `mesa_examples/` — 4 ABM clásicos sin LLM

Para mostrar en la sección 2 (ABM tradicionales) qué se puede hacer con
**Mesa puro**, antes de meter LLMs en la mezcla. Cada modelo es un único
script self-contained que genera PNG + GIF.

| Modelo | Qué muestra |
| --- | --- |
| `schelling.py` | Segregación emergente desde preferencias suaves |
| `sir.py` | Curvas epidémicas SIR sobre una grilla |
| `boids.py` | Flocking de Reynolds en espacio continuo |
| `sugarscape.py` | Recursos, metabolismo, desigualdad (Gini) |

Setup y detalles → [`mesa_examples/README.md`](mesa_examples/README.md).

### `mesa_llm_template/` — la plantilla de la práctica

Pensada para los 35 minutos de actividad guiada (sección 7). Pone a 12
agentes consumidores en un mercado simulado donde **cada decisión la toma
un LLM** (no reglas), y permite cambiar la persona, el prompt y los
parámetros en vivo.

Diseñada para correr en **3 modos**:

```powershell
# 1. 100% offline (sin internet, sin API key) — fallback determinístico
python mesa_llm_template/examples/opcion_a_consumidor.py --provider mock --steps 15

# 2. OpenAI / Anthropic
$env:OPENAI_API_KEY = "sk-..."
python mesa_llm_template/examples/opcion_a_consumidor.py --provider openai --steps 15

# 3. Ollama local (recomendado en clase)
$env:OLLAMA_HOST = "http://localhost:11434"
$env:OLLAMA_MODEL = "llama3.2:3b"
python mesa_llm_template/examples/opcion_a_consumidor.py --provider ollama --steps 15
```

Setup, prompts editables y opción avanzada (tráfico urbano) →
[`mesa_llm_template/README.md`](mesa_llm_template/README.md).

> Cada corrida vuelca a `mesa_llm_template/examples/output/`:
> un PNG con los plots, un **JSONL** con cada llamada al LLM
> (prompt + raw response + parsed) y un **markdown** legible
> con la tabla de decisiones por step. Útil para revisar las
> "razones" que dio el modelo en cada turno.

## Setup rápido

Hay un `.venv/` propio dentro de esta carpeta para aislar las dependencias
de Mesa de las del resto de la materia.

```powershell
cd clase8
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r mesa_examples/requirements.txt
pip install -r mesa_llm_template/requirements.txt
```

Para la práctica con Ollama:

```powershell
# Instalar Ollama desde https://ollama.com
ollama pull llama3.2:3b      # ~2 GB VRAM, recomendado
# o más liviano si tu GPU es chica:
ollama pull llama3.2:1b      # ~1 GB VRAM, ~3× más rápido
```

## Plan B oficial: el modo `mock`

Si la wifi se cae, las API keys fallan u Ollama se cuelga, **la práctica
sigue corriendo**. El cliente cae automáticamente en `llm/mock.py`, un
"LLM fake" determinístico basado en reglas que respeta la persona del
agente y devuelve JSON válido.

```powershell
python mesa_llm_template/examples/opcion_a_consumidor.py --provider mock
```

Es deliberado: cada alumno corre exactamente la misma simulación
(seed-determinada) y se centra en modificar prompts/personas en vez de
debuggear redes.

## Referencias clave usadas en la clase

- **Generative Agents** (Park et al., Stanford 2023) —
  [arXiv:2304.03442](https://arxiv.org/abs/2304.03442)
- **ChatDev / Multi-agent collaboration** (Qian et al.) —
  [arXiv:2307.07924](https://arxiv.org/abs/2307.07924)
- **ReAct** (Yao et al.) —
  [arXiv:2210.03629](https://arxiv.org/abs/2210.03629)
- **Mesa** (Python ABM framework) —
  [github.com/projectmesa/mesa](https://github.com/projectmesa/mesa)
- **Schelling, T. (1971)** — *Dynamic Models of Segregation*. Journal of
  Mathematical Sociology.
- **Epstein & Axtell (1996)** — *Growing Artificial Societies*. MIT Press
  (Sugarscape original).

Citas completas y bibliografía extendida al final de `llm_abm.md`.
