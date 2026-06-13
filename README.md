# AI Reading Assistant

MVP for explaining selected text from any app.

Flow:

1. Select text in a PDF, browser, or document.
2. Press `Ctrl+Shift+E`.
3. The desktop client copies the selection.
4. The FastAPI backend sends it to Ollama through LangChain.
5. A small popup shows the explanation.

## Requirements

- Python 3.11+
- Ollama installed and running
- A local model pulled in Ollama, for example:

```bash
ollama pull gemma3
ollama serve
```

On macOS, the desktop hotkey/copy flow may require Accessibility permission for the terminal app you use.

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

Select text anywhere and press `Ctrl+Shift+E`.

If the popup says no text could be copied, restart the desktop client with a
longer copy delay so you have time to release the hotkey before the app sends
`Cmd+C`:

```bash
python -m desktop_client.main --copy-delay 0.5
```

On macOS, also confirm Accessibility permission is enabled for the app that
launched the desktop client, such as Terminal, iTerm, or VS Code.

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
