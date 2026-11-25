"""Publicação assíncrona de eventos nos webhooks do n8n (implementação completa na issue #2)."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def publicar_evento(webhook_path: str, payload: dict[str, Any]) -> None:
    """Stub inicial do PR 0; a issue #2 implementa o envio HTTP em BackgroundTasks."""
    logger.info(
        "Stub publicar_evento acionado webhook=%s event_id=%s trace_id=%s",
        webhook_path,
        payload.get("event_id"),
        payload.get("trace_id"),
    )
