"""Publicação assíncrona de eventos nos webhooks do n8n (issue #2 / T0006)."""

from __future__ import annotations

import importlib
import logging
import os
import re
import ssl
import threading
import traceback
from collections.abc import Callable
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any
from uuid import uuid4

import httpx
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.schemas.events import DlqErrorInfo, DlqEvent, DlqRequestInfo

logger = logging.getLogger(__name__)

_SUPPORTED_LANGUAGES: dict[str, str] = {
    "pt-br": "pt-BR",
    "en": "en",
    "es": "es",
    "fr": "fr",
    "zh-cn": "zh-CN",
    "hi": "hi",
    "ar": "ar",
    "ru": "ru",
}
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")

_dlq_counter_lock = threading.Lock()
_dlq_events_total = 0
_ssl_context_lock = threading.Lock()


@lru_cache(maxsize=4)
def _criar_ssl_context_cacheado(
    _ssl_cert_file: str,
    _ssl_cert_dir: str,
) -> ssl.SSLContext:
    return httpx.create_ssl_context()


def _obter_ssl_context_n8n(
    ssl_cert_file: str,
    ssl_cert_dir: str,
) -> ssl.SSLContext:
    """Obtém ``SSLContext`` reutilizável sem reparsear o bundle CA a cada envio."""
    with _ssl_context_lock:
        return _criar_ssl_context_cacheado(ssl_cert_file, ssl_cert_dir)


def limpar_cache_ssl_n8n() -> None:
    """Limpa o cache do contexto TLS do cliente dedicado ao n8n (uso em testes)."""
    with _ssl_context_lock:
        _criar_ssl_context_cacheado.cache_clear()


def obter_total_eventos_dlq() -> int:
    """Retorna o total de eventos DLQ enviados com sucesso neste processo."""
    with _dlq_counter_lock:
        return _dlq_events_total


def resetar_total_eventos_dlq() -> None:
    """Zera o contador em memória de eventos DLQ (uso em testes)."""
    global _dlq_events_total
    with _dlq_counter_lock:
        _dlq_events_total = 0


def _incrementar_eventos_dlq() -> None:
    global _dlq_events_total
    with _dlq_counter_lock:
        _dlq_events_total += 1


def resolver_idioma_seguro(accept_language: str | None) -> str:
    """Resolve Accept-Language para um dos 8 códigos do contrato i18n.md.

    Delega para ``app.services.idioma.resolver_idioma`` quando disponível (#13a),
    mantendo fallback idêntico e seguro para nunca ecoar cabeçalhos arbitrários.
    """
    try:
        modulo_idioma = importlib.import_module("app.services.idioma")
        resolvedor = getattr(modulo_idioma, "resolver_idioma", None)
        if callable(resolvedor):
            resultado = resolvedor(accept_language)
            if isinstance(resultado, str) and resultado in _SUPPORTED_LANGUAGES.values():
                return resultado
    except ModuleNotFoundError:
        pass

    if not accept_language or len(accept_language.encode("utf-8")) > 128:
        return "pt-BR"

    primeiro = accept_language.split(",", 1)[0].strip()
    if not primeiro:
        return "pt-BR"

    partes = [parte.strip() for parte in primeiro.split(";")]
    codigo = partes[0].lower()
    for parametro in partes[1:]:
        if not parametro.startswith("q="):
            return "pt-BR"
        try:
            peso = float(parametro[2:])
        except ValueError:
            return "pt-BR"
        if not (0.0 < peso <= 1.0):
            return "pt-BR"

    return _SUPPORTED_LANGUAGES.get(codigo, "pt-BR")


def _sanitizar_texto_erro(texto: str, limite: int) -> str:
    """Remove padrões óbvios de e-mail/credencial Bearer e aplica truncamento."""
    limpo = _EMAIL_RE.sub("[email-redigido]", texto)
    limpo = _BEARER_RE.sub("Bearer [redigido]", limpo)
    return limpo[:limite]


def _nome_tipo_excecao(exc: BaseException) -> str:
    cls = type(exc)
    modulo = cls.__module__
    if not modulo or modulo == "builtins":
        return cls.__qualname__
    return f"{modulo}.{cls.__qualname__}"


def construir_evento_dlq(
    *,
    exc: BaseException,
    trace_id: str,
    method: str,
    route: str,
    status_code: int = 500,
    language: str | None = "pt-BR",
    is_test: bool = False,
) -> dict[str, Any]:
    """Monta e valida um payload ``DlqEvent`` sem dados pessoais da requisição."""
    settings = get_settings()
    mensagem = _sanitizar_texto_erro(str(exc), 500)
    pilha_bruta = "".join(traceback.format_exception(exc))
    pilha = _sanitizar_texto_erro(pilha_bruta, 3000)

    evento = DlqEvent(
        event_id=uuid4(),
        occurred_at=datetime.now(UTC),
        trace_id=trace_id,
        environment=settings.app_env,
        is_test=is_test,
        request=DlqRequestInfo(
            method=method.upper(),
            route=route,
            status_code=status_code,
            language=language,
        ),
        error=DlqErrorInfo(
            type=_nome_tipo_excecao(exc),
            message=mensagem,
            stack_trace=pilha,
        ),
    )
    return evento.model_dump(mode="json", exclude_none=True)


async def publicar_evento(webhook_path: str, payload: dict[str, Any]) -> None:
    """Envia evento assíncrono para um webhook do n8n sem jamais propagar falhas.

    Usa ``httpx.AsyncClient`` dedicado com timeout curto para não competir com o
    pool compartilhado da aplicação nem bloquear o planejamento de viagens.
    """
    caminho = webhook_path.strip("/")
    event_id = payload.get("event_id")
    trace_id = payload.get("trace_id")

    try:
        settings = get_settings()
        base_url = settings.n8n_webhook_base_url.strip()
        if not base_url:
            logger.info(
                "Modo local (N8N_WEBHOOK_BASE_URL vazia): evento enviado apenas ao log "
                "webhook=%s event_id=%s trace_id=%s",
                caminho,
                event_id,
                trace_id,
            )
            return

        url = f"{base_url.rstrip('/')}/{caminho}"
        logger.info(
            "Iniciando envio de evento ao n8n webhook=%s event_id=%s trace_id=%s",
            caminho,
            event_id,
            trace_id,
        )
        ssl_context = await run_in_threadpool(
            _obter_ssl_context_n8n,
            os.environ.get("SSL_CERT_FILE", ""),
            os.environ.get("SSL_CERT_DIR", ""),
        )
        async with httpx.AsyncClient(
            timeout=settings.n8n_timeout_seconds,
            verify=ssl_context,
        ) as client:
            response = await client.post(
                url,
                json=payload,
                headers={"X-Webhook-Secret": settings.n8n_webhook_secret},
            )
            response.raise_for_status()

        if caminho == "turismo-dlq":
            _incrementar_eventos_dlq()

        logger.info(
            "Concluído: evento enviado ao n8n webhook=%s status=%s event_id=%s trace_id=%s",
            caminho,
            response.status_code,
            event_id,
            trace_id,
        )
    except Exception:
        logger.exception(
            "falha ao publicar evento no n8n webhook=%s event_id=%s trace_id=%s",
            caminho,
            event_id,
            trace_id,
        )


async def executar_tarefa_com_dlq(
    func: Callable[..., Any],
    *args: Any,
    trace_id: str,
    method: str,
    route: str,
    language: str = "pt-BR",
) -> None:
    """Executa função síncrona em threadpool e despacha falhas para a DLQ."""
    try:
        await run_in_threadpool(func, *args)
    except Exception as exc:
        logger.exception(
            "Falha em tarefa de fundo route=%s trace_id=%s",
            route,
            trace_id,
        )
        payload = construir_evento_dlq(
            exc=exc,
            trace_id=trace_id,
            method=method,
            route=route,
            status_code=500,
            language=language,
            is_test=False,
        )
        await publicar_evento("turismo-dlq", payload)
