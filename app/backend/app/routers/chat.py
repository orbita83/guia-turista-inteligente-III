"""Router de diálogo com IA para montagem de roteiro — implementado por P4 na issue #11 (T0012)."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])
