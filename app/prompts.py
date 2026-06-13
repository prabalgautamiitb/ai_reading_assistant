from app.schemas import ExplainMode

SUPPORTED_MODES: tuple[ExplainMode, ...] = (
    "simple",
    "summary",
    "technical",
    "example",
)

SYSTEM_PROMPT = (
    "You are an AI reading assistant. Help the user understand selected text. "
    "Be accurate, concise, and use plain language. If the text is ambiguous, "
    "state the likely meaning instead of pretending certainty."
)

MODE_INSTRUCTIONS: dict[ExplainMode, str] = {
    "simple": (
        "Explain the selected text in simple terms. Use a short example if it helps. "
        "Keep the answer under 180 words."
    ),
    "summary": (
        "Summarize the selected text into the key idea and any important details. "
        "Keep the answer under 120 words."
    ),
    "technical": (
        "Explain the selected text technically, preserving important terminology. "
        "Keep the answer under 220 words."
    ),
    "example": (
        "Explain the selected text mostly through one concrete example or analogy. "
        "Keep the answer under 180 words."
    ),
}


def build_user_prompt(text: str, mode: ExplainMode) -> str:
    if mode not in MODE_INSTRUCTIONS:
        raise ValueError(f"Unsupported mode: {mode}")

    return f"{MODE_INSTRUCTIONS[mode]}\n\nSelected text:\n{text.strip()}"
