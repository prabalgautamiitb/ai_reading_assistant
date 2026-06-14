# AI Reading Assistant

MVP for explaining selected text from any app.

Flow:

1. Select text in a PDF, browser, or document.
2. Press Right Shift twice.
3. The desktop client copies the selection.
4. The FastAPI backend sends it to Ollama through LangChain.
5. A small overlay appears near your selection with the explanation.

## Requirements

- Python 3.11+
- Ollama installed and running
- A local model pulled in Ollama, for example:

```bash
ollama pull gemma3
ollama serve
```

On macOS, the desktop double-press/copy flow may require Accessibility permission for the terminal app you use.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

## Run Backend

```bash
uvicorn app.main:app --reload
```

The default model is `gemma3:latest` because that model is already available on this machine. Change `OLLAMA_MODEL` in `.env` if you want to use another local Ollama model.

Test directly:

```bash
curl -X POST http://127.0.0.1:8000/api/explain \
  -H "Content-Type: application/json" \
  -d '{"text":"A language model encodes statistical information about one or more languages.","mode":"simple"}'
```

## Run Desktop Client

In a second terminal:

```bash
python -m desktop_client.main
```

Select text anywhere and press Right Shift twice. On macOS, the answer appears
in a non-activating overlay near the cursor, so the current PDF or document
should stay in front.

Right Shift is the default because Space scrolls many PDF readers. Configure the
desktop client in `.env`:

```dotenv
DESKTOP_BACKEND_URL="http://127.0.0.1:8000"
DESKTOP_TRIGGER_KEY="shift_r"
DESKTOP_DOUBLE_PRESS_WINDOW="0.35"
DESKTOP_COPY_DELAY="0.25"
DESKTOP_COPY_TIMEOUT="2.0"
DESKTOP_MODE="simple"
```

For example, to use Left Shift instead:

```dotenv
DESKTOP_TRIGGER_KEY="shift_l"
```

If the popup says no text could be copied, restart the desktop client with a
longer copy delay before the app sends `Cmd+C`:

```dotenv
DESKTOP_COPY_DELAY="0.5"
```

On macOS, also confirm Accessibility permission is enabled for the app that
launched the desktop client, such as Terminal, iTerm, or VS Code.

Command-line flags such as `--trigger-key shift_l` still work as temporary
overrides for the `.env` values.

## API

- `GET /health`
- `GET /api/actions`
- `POST /api/explain`

Request body:

```json
{
  "text": "Text to explain",
  "mode": "simple"
}
```

Available modes:

- `simple`
- `summary`
- `technical`
- `example`

## Extending Providers

Provider implementations live in `app/llm/providers/`. Add a new provider class that implements `LLMProvider`, then register it in `app/llm/factory.py`.
