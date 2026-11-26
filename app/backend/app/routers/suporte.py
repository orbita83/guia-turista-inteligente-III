"""Router de suporte operacional (ChatOps) — entrega 4a (T0007 / issue #4)."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.schemas.events import DlqErrorInfo, DlqEvent, DlqRequestInfo
from app.services.events import publicar_evento


def exigir_chave_suporte(request: Request) -> None:
    """Autentica exclusivamente por X-Support-Key em tempo constante (UTF-8 bytes)."""
    esperado = get_settings().support_api_key
    if not esperado or not esperado.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Serviço de suporte não configurado.",
        )

    recebido = request.headers.get("X-Support-Key")
    if not recebido or not secrets.compare_digest(
        recebido.encode("utf-8"), esperado.encode("utf-8")
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Não autorizado.",
        )


router = APIRouter(
    prefix="/api/v1/suporte",
    tags=["suporte"],
    dependencies=[Depends(exigir_chave_suporte)],
)


class SupportDependencyStatus(BaseModel):
    name: str
    state: Literal["closed", "open", "half_open"]


class SupportStatusResponse(BaseModel):
    status: Literal["ok", "degraded", "down"]
    checked_at: str
    dependencies: list[SupportDependencyStatus]


class SupportUptimeResponse(BaseModel):
    started_at: str
    uptime_seconds: int = Field(ge=0)
    uptime_human: str


class SupportTelemetryResponse(BaseModel):
    requests_total: int
    errors_total: int
    latency_p95_ms: float | None = None
    in_flight: int
    dlq_events_total: int


class SupportTestDlqResponse(BaseModel):
    trace_id: str
    scheduled: Literal[True] = True


@router.get("/status", response_model=SupportStatusResponse)
async def obter_status_suporte() -> SupportStatusResponse:
    """Saúde geral e estado dos disjuntores (4a: resposta de contrato para o ChatOps)."""
    return SupportStatusResponse(
        status="ok",
        checked_at="2026-11-26T00:00:00Z",
        dependencies=[
            SupportDependencyStatus(name="weather", state="closed"),
            SupportDependencyStatus(name="guide", state="closed"),
        ],
    )


@router.get("/uptime", response_model=SupportUptimeResponse)
async def obter_uptime_suporte() -> SupportUptimeResponse:
    """Tempo de atividade do processo (4a: resposta de contrato para o ChatOps)."""
    return SupportUptimeResponse(
        started_at="2026-11-26T00:00:00Z",
        uptime_seconds=8040,
        uptime_human="2h 14min",
    )


@router.get("/telemetria", response_model=SupportTelemetryResponse)
async def obter_telemetria_suporte() -> SupportTelemetryResponse:
    """Métricas operacionais internas (4a: resposta de contrato para o ChatOps)."""
    return SupportTelemetryResponse(
        requests_total=0,
        errors_total=0,
        latency_p95_ms=None,
        in_flight=1,
        dlq_events_total=0,
    )


@router.post(
    "/testardlq",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SupportTestDlqResponse,
)
async def disparar_teste_dlq(
    request: Request,
    background_tasks: BackgroundTasks,
) -> SupportTestDlqResponse:
    """Agenda falha simulada em BackgroundTasks correlacionada ao X-Request-ID."""
    trace_id = getattr(request.state, "request_id", None) or uuid4().hex
    settings = get_settings()
    evento = DlqEvent(
        event_id=uuid4(),
        occurred_at=datetime.now(UTC),
        trace_id=trace_id,
        environment=settings.app_env,
        is_test=True,
        request=DlqRequestInfo(
            method="POST",
            route="/api/v1/suporte/testardlq",
            status_code=500,
            language="pt-BR",
        ),
        error=DlqErrorInfo(
            type="RuntimeError",
            message="Falha simulada para teste da DLQ",
            stack_trace="RuntimeError: Falha simulada para teste da DLQ\n",
        ),
    )
    payload = evento.model_dump(mode="json", exclude_none=True)
    background_tasks.add_task(publicar_evento, "turismo-dlq", payload)
    return SupportTestDlqResponse(trace_id=trace_id, scheduled=True)
