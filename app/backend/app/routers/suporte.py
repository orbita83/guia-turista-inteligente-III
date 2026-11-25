"""Router de suporte operacional (ChatOps) — implementado na issue #4 (T0007)."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/suporte", tags=["suporte"])
