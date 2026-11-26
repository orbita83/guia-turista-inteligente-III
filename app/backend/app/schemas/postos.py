"""Entrada, catálogo local e resposta da consulta de postos ANP."""

from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.services.postos_service import LIMITE_LAT_BRASIL, LIMITE_LON_BRASIL

MAX_PONTOS_ROTA = 10_000

LatitudeBrasil = Annotated[
    float, Field(strict=True, ge=LIMITE_LAT_BRASIL[0], le=LIMITE_LAT_BRASIL[1])
]
LongitudeBrasil = Annotated[
    float, Field(strict=True, ge=LIMITE_LON_BRASIL[0], le=LIMITE_LON_BRASIL[1])
]
PontoRota = tuple[LatitudeBrasil, LongitudeBrasil]


class ConsultaPostos(BaseModel):
    model_config = ConfigDict(extra="forbid")

    geometria: list[PontoRota] = Field(min_length=2, max_length=MAX_PONTOS_ROTA)
    raio_km: float = Field(default=2.0, strict=True, gt=0, le=5)


class PostoANP(BaseModel):
    cnpj: str = Field(pattern=r"^[0-9]{2}\.[0-9]{3}\.[0-9]{3}/[0-9]{4}-[0-9]{2}$")
    legal_name: str = Field(min_length=1)
    rating: float | None = Field(ge=0, le=5)
    authorized_since: date
    authorization_years: int = Field(ge=0)
    fuels: list[str]
    latitude: LatitudeBrasil
    longitude: LongitudeBrasil


class PostoCatalogo(PostoANP):
    data_reference_date: date


class PostoRanqueado(PostoANP):
    distance_from_route_km: float = Field(ge=0)
    rank: int = Field(ge=1)


class ResultadoPostos(BaseModel):
    postos: list[PostoRanqueado]
    data_reference_date: date


class ErroPostos(BaseModel):
    detail: str
