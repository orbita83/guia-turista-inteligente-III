"""Router de diálogo com IA para montagem de roteiro — implementado por P4 na issue #11 (T0012)."""

from __future__ import annotations

import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.circuit_breaker import CircuitBreaker
from app.core.config import Settings, get_settings
from app.core.dependencies import get_circuit_breakers, get_current_user
from app.schemas.chat import RequisicaoChat, RespostaChat
from app.services.guide import (
    _resolver_idioma_compat,
    conversar_roteiro,
    montar_instrucao_idioma_chat,
)

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

MAX_CHAT_MESSAGES_PER_HOUR = 20
CHAT_RATE_LIMIT_WINDOW_SECONDS = 3600.0
_HISTORICO_MENSAGENS_POR_SESSAO: dict[str, list[float]] = {}


def limpar_rate_limit_chat() -> None:
    """Limpa o contador em memória de mensagens por sessão (usado em testes)."""
    _HISTORICO_MENSAGENS_POR_SESSAO.clear()


def obter_idioma_requisicao(request: Request) -> str:
    """Extrai e resolve o idioma da requisição a partir do cabeçalho Accept-Language."""
    return _resolver_idioma_compat(request.headers.get("accept-language"))


def preparar_instrucao_idioma_chat(request: Request) -> str:
    """Resolve o Accept-Language da requisição e monta a diretriz de idioma do prompt."""
    idioma = obter_idioma_requisicao(request)
    return montar_instrucao_idioma_chat(idioma)


def _chave_sessao_chat(request: Request, user: dict[str, Any]) -> str:
    session_id = request.session.get("session_id")
    if isinstance(session_id, str) and session_id.strip():
        return f"session:{session_id.strip()}"
    user_id = str(user.get("id") or "anon")
    return f"user:{user_id}"


def _verificar_cota_sessao(request: Request, user: dict[str, Any]) -> None:
    """Limita cada sessão a no máximo 20 mensagens por hora para proteger a cota do Gemini."""
    agora = time.monotonic()
    chave = _chave_sessao_chat(request, user)
    timestamps = _HISTORICO_MENSAGENS_POR_SESSAO.get(chave, [])
    recentes = [
        instante
        for instante in timestamps
        if agora - instante < CHAT_RATE_LIMIT_WINDOW_SECONDS
    ]
    if len(recentes) >= MAX_CHAT_MESSAGES_PER_HOUR:
        _HISTORICO_MENSAGENS_POR_SESSAO[chave] = recentes
        raise HTTPException(
            status_code=429,
            detail=(
                "Você atingiu o limite de 20 mensagens por hora nesta sessão. "
                "Aguarde alguns minutos antes de enviar uma nova mensagem."
            ),
        )
    recentes.append(agora)
    _HISTORICO_MENSAGENS_POR_SESSAO[chave] = recentes


@router.post("/mensagens", response_model=RespostaChat)
async def enviar_mensagem_chat(
    payload: RequisicaoChat,
    request: Request,
    user: Annotated[dict[str, Any], Depends(get_current_user)],
    breakers: Annotated[dict[str, CircuitBreaker], Depends(get_circuit_breakers)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> RespostaChat:
    """Conduz o diálogo com a IA para montar um roteiro personalizado.

    Contrato (`POST /api/v1/chat/mensagens`, exige sessão autenticada):
    - Entrada: `{"messages": [{"role": "user"|"assistant", "content": "..."}], "origin": "...", "destination": "..."}`
      (máx. 12 mensagens de até 1000 caracteres; `origin` e `destination` até 100 caracteres).
    - Saída: `{"reply": "...", "done": false, "itinerary": null}` durante as perguntas guiadas
      (ritmo -> acompanhantes -> gastronomia) ou `{"reply": "...", "done": true, "itinerary": {...}}`
      validado contra `Itinerary` (`schemas/events.py`).
    - Fallback: sem `GEMINI_API_KEY`, com circuit breaker `guide` aberto ou em falha/timeout,
      responde `200` com perguntas e roteiro por regras locais.
    - Rate limit: máximo de 20 mensagens por sessão por hora (`429`).
    """
    _verificar_cota_sessao(request, user)
    idioma = obter_idioma_requisicao(request)
    resultado = await conversar_roteiro(
        messages=[mensagem.model_dump() for mensagem in payload.messages],
        origin=payload.origin,
        destination=payload.destination,
        api_key=settings.gemini_api_key,
        timeout_seconds=settings.gemini_timeout_seconds,
        accept_language=idioma,
        circuit_breaker=breakers["guide"],
    )
    return RespostaChat.model_validate(resultado)
