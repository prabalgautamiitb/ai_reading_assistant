from fastapi import APIRouter, HTTPException, status

from app.llm.factory import get_provider
from app.prompts import SUPPORTED_MODES
from app.schemas import ExplainRequest, ExplainResponse, HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/api/actions")
def actions() -> dict[str, list[str]]:
    return {"modes": list(SUPPORTED_MODES)}


@router.post("/api/explain", response_model=ExplainResponse)
async def explain(request: ExplainRequest) -> ExplainResponse:
    provider = get_provider(request.provider)

    try:
        answer = await provider.explain(text=request.text, mode=request.mode)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM provider failed: {exc}",
        ) from exc

    return ExplainResponse(
        answer=answer,
        mode=request.mode,
        provider=provider.name,
        model=provider.model_name,
    )
