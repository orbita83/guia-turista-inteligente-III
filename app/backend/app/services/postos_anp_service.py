"""Consulta e ranqueia o catálogo estático de postos ANP."""

import logging
import math
from collections.abc import Sequence
from datetime import date
from functools import lru_cache
from itertools import pairwise
from threading import Lock

from pydantic import TypeAdapter, ValidationError

from app.core.config import BACKEND_ROOT
from app.schemas.postos import PostoCatalogo, PostoRanqueado, ResultadoPostos
from app.services.altimetria_service import RAIO_TERRA_M

logger = logging.getLogger(__name__)
DATA_DIR = BACKEND_ROOT / "static" / "data"
CATALOGO_ADAPTER = TypeAdapter(list[PostoCatalogo])
CATALOGO_LOCK = Lock()
KM_POR_GRAU = math.radians(1) * RAIO_TERRA_M / 1000

Coordenada = tuple[float, float]


class CatalogoPostosIndisponivel(Exception):
    """A base de postos não pôde ser carregada neste ambiente."""


@lru_cache(maxsize=2)
def _carregar_catalogo(permitir_fixture: bool) -> tuple[list[PostoCatalogo], date]:
    try:
        try:
            dados = (DATA_DIR / "postos_pi.json").read_bytes()
        except FileNotFoundError:
            if not permitir_fixture:
                raise
            dados = (DATA_DIR / "postos_fixture.json").read_bytes()
            logger.warning("Base real ANP ausente. Usando postos fictícios no ambiente local.")

        postos = CATALOGO_ADAPTER.validate_json(dados)
        datas = {posto.data_reference_date for posto in postos}
        if len(datas) != 1:
            raise ValueError("O catálogo deve conter uma única data de referência.")
        return postos, next(iter(datas))
    except (OSError, ValidationError, ValueError) as erro:
        logger.error("Catálogo ANP indisponível (%s).", type(erro).__name__)
        raise CatalogoPostosIndisponivel from erro


def _distancia_ao_segmento(inicio: Coordenada, fim: Coordenada) -> float:
    """Distância da origem a um segmento no plano local, em quilômetros."""
    x, y = inicio
    dx, dy = fim[0] - x, fim[1] - y
    comprimento_quadrado = dx * dx + dy * dy
    if comprimento_quadrado == 0:
        return math.hypot(x, y)

    projecao = -(x * dx + y * dy) / comprimento_quadrado
    t = max(0.0, min(1.0, projecao))
    return math.hypot(x + t * dx, y + t * dy)


def _distancia_a_rota(posto: PostoCatalogo, geometria: Sequence[Coordenada]) -> float:
    # Plano tangente aproximado centrado no posto para raios de até poucos quilômetros.
    km_por_grau_lon = KM_POR_GRAU * math.cos(math.radians(posto.latitude))
    pontos = (
        ((lon - posto.longitude) * km_por_grau_lon, (lat - posto.latitude) * KM_POR_GRAU)
        for lat, lon in geometria
    )
    return min(_distancia_ao_segmento(a, b) for a, b in pairwise(pontos))


def _chave_ranqueamento(item: tuple[PostoCatalogo, float]) -> tuple[bool, float, int, float, str]:
    posto, distancia = item
    return (
        posto.rating is None,
        -(posto.rating if posto.rating is not None else 0.0),
        -posto.authorization_years,
        distancia,
        posto.cnpj,
    )


def consultar_postos(
    geometria: Sequence[Coordenada], raio_km: float, *, app_env: str
) -> ResultadoPostos:
    # Impede leituras duplicadas quando as primeiras requisições chegam juntas.
    with CATALOGO_LOCK:
        postos, data_referencia = _carregar_catalogo(app_env == "local")

    candidatos = []
    for posto in postos:
        distancia = _distancia_a_rota(posto, geometria)
        if distancia <= raio_km:
            candidatos.append((posto, distancia))

    candidatos.sort(key=_chave_ranqueamento)
    return ResultadoPostos(
        postos=[
            PostoRanqueado(
                **posto.model_dump(exclude={"data_reference_date"}),
                distance_from_route_km=distancia,
                rank=rank,
            )
            for rank, (posto, distancia) in enumerate(candidatos, start=1)
        ],
        data_reference_date=data_referencia,
    )
