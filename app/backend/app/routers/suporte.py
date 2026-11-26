"""Router de suporte operacional (ChatOps) — entrega 4b (T0007 / issue #4)."""

from __future__ import annotations

import math
import secrets
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.services.events import (
    construir_evento_dlq,
    obter_total_eventos_dlq,
    publicar_evento,
    resolver_idioma_seguro,
)


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


def formatar_uptime_humano(segundos: int) -> str:
    """Formata segundos em representação curta como ``2h 14min``."""
    segundos = max(0, segundos)
    dias, resto = divmod(segundos, 86400)
    horas, resto = divmod(resto, 3600)
    minutos = resto // 60
    if dias > 0:
        return f"{dias}d {horas}h {minutos}min"
    if horas > 0:
        return f"{horas}h {minutos}min"
    return f"{minutos}min"


def _calcular_p95_histograma_ms(histograma: Any) -> float | None:
    """Estima o p95 global em ms por interpolação linear nos buckets Prometheus."""
    if histograma is None or not hasattr(histograma, "collect"):
        return None

    contagem_total = 0.0
    buckets_acumulados: dict[float, float] = {}

    for metrica in histograma.collect():
        for sample in metrica.samples:
            if sample.name.endswith("_count"):
                contagem_total += float(sample.value)
            elif sample.name.endswith("_bucket"):
                le_raw = sample.labels.get("le", "")
                if le_raw in {"+Inf", "Inf"}:
                    continue
                try:
                    limite = float(le_raw)
                except ValueError:
                    continue
                if math.isfinite(limite):
                    buckets_acumulados[limite] = buckets_acumulados.get(
                        limite, 0.0
                    ) + float(sample.value)

    if contagem_total <= 0 or not buckets_acumulados:
        return None

    alvo = 0.95 * contagem_total
    limite_anterior = 0.0
    contagem_anterior = 0.0

    for limite in sorted(buckets_acumulados):
        contagem = buckets_acumulados[limite]
        if contagem >= alvo:
            delta_contagem = contagem - contagem_anterior
            if delta_contagem <= 0:
                return round(limite * 1000.0, 3)
            fracao = (alvo - contagem_anterior) / delta_contagem
            segundos_p95 = limite_anterior + (limite - limite_anterior) * fracao
            return round(max(0.0, segundos_p95) * 1000.0, 3)
        limite_anterior = limite
        contagem_anterior = contagem

    return round(limite_anterior * 1000.0, 3)


@router.get("/status", response_model=SupportStatusResponse)
async def obter_status_suporte(request: Request) -> SupportStatusResponse:
    """Saúde geral do processo e estado real dos disjuntores."""
    checked_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    breakers = getattr(request.app.state, "circuit_breakers", None)
    if not isinstance(breakers, dict):
        return SupportStatusResponse(
            status="down",
            checked_at=checked_at,
            dependencies=[],
        )

    dependencias = [
        SupportDependencyStatus(name=str(nome), state=breaker.state.value)
        for nome, breaker in breakers.items()
    ]
    estado_geral: Literal["ok", "degraded"] = (
        "ok" if all(dep.state == "closed" for dep in dependencias) else "degraded"
    )
    return SupportStatusResponse(
        status=estado_geral,
        checked_at=checked_at,
        dependencies=dependencias,
    )


@router.get("/uptime", response_model=SupportUptimeResponse)
async def obter_uptime_suporte(request: Request) -> SupportUptimeResponse:
    """Tempo decorrido desde a inicialização do processo atual."""
    iniciado_mono = getattr(request.app.state, "started_at", None)
    uptime_seconds = (
        int(max(0.0, monotonic() - iniciado_mono))
        if isinstance(iniciado_mono, (int, float))
        else 0
    )

    iniciado_utc = getattr(request.app.state, "started_at_utc", None)
    if isinstance(iniciado_utc, datetime):
        started_at = iniciado_utc.astimezone(UTC).isoformat().replace("+00:00", "Z")
    else:
        started_at = (
            (datetime.now(UTC) - timedelta(seconds=uptime_seconds))
            .isoformat()
            .replace("+00:00", "Z")
        )

    return SupportUptimeResponse(
        started_at=started_at,
        uptime_seconds=uptime_seconds,
        uptime_human=formatar_uptime_humano(uptime_seconds),
    )


@router.get("/telemetria", response_model=SupportTelemetryResponse)
async def obter_telemetria_suporte(request: Request) -> SupportTelemetryResponse:
    """Métricas operacionais reais agregadas a partir do registro Prometheus."""
    contador_http = getattr(request.app.state, "http_requests_counter", None)
    requests_total = 0
    errors_total = 0

    if contador_http is not None and hasattr(contador_http, "collect"):
        for metrica in contador_http.collect():
            for sample in metrica.samples:
                if sample.name != "http_requests_total":
                    continue
                valor = round(float(sample.value))
                requests_total += valor
                codigo_str = sample.labels.get("status", "")
                if codigo_str.isdigit() and int(codigo_str) >= 500:
                    errors_total += valor

    histograma_latencia = getattr(request.app.state, "http_latency_histogram", None)
    latency_p95_ms = _calcular_p95_histograma_ms(histograma_latencia)

    leitor_in_flight = getattr(request.app.state, "get_in_flight_requests", None)
    in_flight = int(leitor_in_flight()) if callable(leitor_in_flight) else 0

    return SupportTelemetryResponse(
        requests_total=requests_total,
        errors_total=errors_total,
        latency_p95_ms=latency_p95_ms,
        in_flight=in_flight,
        dlq_events_total=obter_total_eventos_dlq(),
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
    """Agenda falha simulada (is_test=True) correlacionada ao X-Request-ID."""
    trace_id = getattr(request.state, "request_id", None) or uuid4().hex
    idioma = resolver_idioma_seguro(request.headers.get("accept-language"))
    payload = construir_evento_dlq(
        exc=RuntimeError("Falha simulada para teste da DLQ"),
        trace_id=trace_id,
        method="POST",
        route="/api/v1/suporte/testardlq",
        status_code=500,
        language=idioma,
        is_test=True,
    )
    background_tasks.add_task(publicar_evento, "turismo-dlq", payload)
    return SupportTestDlqResponse(trace_id=trace_id, scheduled=True)
