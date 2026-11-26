"""Router de diálogo com IA para montagem de roteiro — implementado por P4 na issue #11 (T0012)."""

from fastapi import APIRouter, Request

from app.services.guide import montar_instrucao_idioma_chat
from app.services.idioma import resolver_idioma

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


def obter_idioma_requisicao(request: Request) -> str:
    """Extrai e resolve o idioma da requisição a partir do cabeçalho Accept-Language."""
    return resolver_idioma(request.headers.get("accept-language"))


def preparar_instrucao_idioma_chat(request: Request) -> str:
    """Resolve o Accept-Language da requisição e monta a diretriz de idioma do prompt."""
    idioma = obter_idioma_requisicao(request)
    return montar_instrucao_idioma_chat(idioma)

