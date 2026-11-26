"""Schemas HTTP do diálogo com IA — implementados por P4 na issue #11 (T0012)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.events import Itinerary
from app.services.trips import sanitize_input

MAX_MESSAGES_PER_REQUEST = 12
MAX_MESSAGE_CONTENT_LENGTH = 1000
MAX_LOCATION_LENGTH = 100


def _validar_e_higienizar_texto(
    valor: str,
    *,
    max_length: int,
    nome_campo: str,
) -> str:
    texto_bruto = valor.strip()
    if not texto_bruto:
        raise ValueError(f"O campo '{nome_campo}' não pode ser vazio.")
    if len(texto_bruto) > max_length:
        raise ValueError(
            f"O campo '{nome_campo}' excede o limite de {max_length} caracteres."
        )
    higienizado = sanitize_input(texto_bruto, max_length=max_length)
    if not higienizado:
        raise ValueError(
            f"O campo '{nome_campo}' não contém texto válido após higienização."
        )
    return higienizado


class MensagemChat(BaseModel):
    """Mensagem individual trocada no diálogo de planejamento de roteiro."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str

    @field_validator("content", mode="after")
    @classmethod
    def validar_content(cls, valor: str) -> str:
        return _validar_e_higienizar_texto(
            valor,
            max_length=MAX_MESSAGE_CONTENT_LENGTH,
            nome_campo="content",
        )


class RequisicaoChat(BaseModel):
    """Corpo de entrada de POST /api/v1/chat/mensagens.

    O cliente mantém o histórico da conversa; o backend não persiste estado do diálogo.
    Limites: até 12 mensagens (máx. 1000 caracteres cada) e origin/destination até 100 caracteres.
    """

    model_config = ConfigDict(extra="forbid")

    messages: list[MensagemChat] = Field(
        min_length=1,
        max_length=MAX_MESSAGES_PER_REQUEST,
    )
    origin: str
    destination: str

    @field_validator("origin", mode="after")
    @classmethod
    def validar_origin(cls, valor: str) -> str:
        return _validar_e_higienizar_texto(
            valor,
            max_length=MAX_LOCATION_LENGTH,
            nome_campo="origin",
        )

    @field_validator("destination", mode="after")
    @classmethod
    def validar_destination(cls, valor: str) -> str:
        return _validar_e_higienizar_texto(
            valor,
            max_length=MAX_LOCATION_LENGTH,
            nome_campo="destination",
        )


class RespostaChat(BaseModel):
    """Resposta estruturada do endpoint POST /api/v1/chat/mensagens."""

    model_config = ConfigDict(extra="forbid")

    reply: str = Field(min_length=1)
    done: bool = False
    itinerary: Itinerary | None = None
