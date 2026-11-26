"""Consulta autenticada de postos ANP ao longo da polilinha de uma rota."""

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from app.core.config import get_settings
from app.core.dependencies import get_current_user
from app.schemas.postos import ConsultaPostos, ErroPostos, ResultadoPostos
from app.services.postos_anp_service import CatalogoPostosIndisponivel, consultar_postos


class RotaPostos(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def tratar_validacao(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError:
                raise HTTPException(
                    status_code=422, detail="Geometria ou raio de busca inválido."
                ) from None

        return tratar_validacao


router = APIRouter(prefix="/api/v1/postos", tags=["postos"], route_class=RotaPostos)


@router.post(
    "/ao-longo-da-rota",
    dependencies=[Depends(get_current_user)],
    responses={401: {"model": ErroPostos}, 422: {"model": ErroPostos}, 503: {"model": ErroPostos}},
)
def postos_ao_longo_da_rota(consulta: ConsultaPostos) -> ResultadoPostos:
    try:
        return consultar_postos(
            consulta.geometria, consulta.raio_km, app_env=get_settings().app_env
        )
    except CatalogoPostosIndisponivel:
        raise HTTPException(status_code=503, detail="Catálogo de postos indisponível.") from None
