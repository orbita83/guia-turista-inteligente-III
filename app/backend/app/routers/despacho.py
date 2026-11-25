"""Router de despacho multicanal de roteiros — implementado por P5 na issue #15 (T0014)."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/despacho", tags=["despacho"])
