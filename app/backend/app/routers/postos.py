"""Router de postos ANP ao longo da rota — implementado por P3 na issue #9 (T0011)."""

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/postos", tags=["postos"])
