# Mesa-LLM template

Plantilla para la **actividad práctica (35 min)** de la clase
*LLMs en Agent-Based Models*. Pensada para que arranques en menos de 2 minutos,
**con o sin API keys**, **con o sin internet**.

## Qué hay acá

```
mesa_llm_template/
├── README.md
├── requirements.txt
├── llm/
│   ├── __init__.py
│   ├── client.py        # cliente unificado (OpenAI/Anthropic/Ollama/Mock)
│   └── mock.py          # LLM "fake" determinístico (corre offline)
├── prompts/
│   ├── consumer.txt     # Opción A — consumidor en un mercado
│   ├── opinion_holder.txt
│   ├── commuter.txt     # Opción B — tráfico urbano
│   ├── trader.txt       # Opción B — negociación
│   └── disaster_citizen.txt   # Opción B — respuesta a desastre
├── data/
│   └── brand_opinions.csv     # 32 opiniones sobre 4 marcas (sintéticas)
├── examples/
│   ├── opcion_a_consumidor.py   # runnable (Opción A)
│   └── opcion_b_trafico.py      # runnable (Opción B)
└── notebook_colab.ipynb
```

## Las dos opciones de la actividad

### Opción A · Fácil (recomendada)

Modificá un agente que **ya está armado** (consumidor en un mercado):

```powershell
python examples/opcion_a_consumidor.py
```

Cosas para tocar:

- Editar `prompts/consumer.txt` (la plantilla del prompt)
- Cambiar las *personas* en `examples/opcion_a_consumidor.py` (lista `PERSONAS`)
- Probar `--steps 30` y mirar cómo cambia la **distribución de compras**

### Opción B · Avanzada

Diseñar un agente nuevo desde cero. Hay tres scaffolds para arrancar:

- `prompts/commuter.txt` + `examples/opcion_b_trafico.py` — tráfico urbano
- `prompts/trader.txt` — negociación de mercado (vos hacés el `mesa.Model`)
- `prompts/disaster_citizen.txt` — respuesta a desastre

## Sin API keys → modo Mock

Si no tenés claves de OpenAI/Anthropic ni Ollama corriendo, **igual funciona**:
el cliente cae en `llm/mock.py`, que es un "LLM fake" basado en reglas que
devuelve JSON válido y respeta la *persona*. Pensado para que la clase corra
aunque la wifi se caiga.

El mock es **determinístico** dada una semilla, así que los resultados son
reproducibles entre alumnos.

## Con API keys → modo real

Setear **una sola** de estas variables y se usa automáticamente:

```powershell
# OpenAI (recomendado)
$env:OPENAI_API_KEY = "sk-..."

# Anthropic (Claude)
$env:ANTHROPIC_API_KEY = "sk-ant-..."

# Ollama local (sin clave, requiere `ollama serve` corriendo)
$env:OLLAMA_HOST = "http://localhost:11434"
$env:OLLAMA_MODEL = "llama3.2"
```

Forzar el provider con `--provider openai|anthropic|ollama|mock`:

```powershell
python examples/opcion_a_consumidor.py --provider mock --steps 25
python examples/opcion_a_consumidor.py --provider openai --model gpt-4o-mini
```

## Instalación

```powershell
# Desde el venv del repo
pip install -r mesa_llm_template/requirements.txt
```

## En Colab

Subí `notebook_colab.ipynb` a [colab.research.google.com](https://colab.research.google.com/),
ejecutá la primera celda (instala dependencias + clona los archivos auxiliares)
y listo.
