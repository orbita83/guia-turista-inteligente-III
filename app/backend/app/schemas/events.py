"""Modelos Pydantic dos contratos de eventos da spec 003 (fonte única)."""

from __future__ import annotations

from datetime import date as CalendarDate
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, model_validator

DLQ_EVENT_EXAMPLE: dict[str, Any] = {
    "event_type": "turismo.falha",
    "event_id": "7d9f1c2e-3b4a-4c5d-8e6f-0a1b2c3d4e5f",
    "occurred_at": "2026-11-19T18:30:00Z",
    "trace_id": "a1b2c3d4e5f64a7b8c9d0e1f2a3b4c5d",
    "environment": "local",
    "is_test": True,
    "request": {
        "method": "POST",
        "route": "/api/v1/suporte/testardlq",
        "status_code": 500,
        "language": "pt-BR",
    },
    "error": {
        "type": "RuntimeError",
        "message": "Falha simulada para teste da DLQ",
        "stack_trace": "Traceback (most recent call last): ...",
    },
}

ITINERARY_EXAMPLE: dict[str, Any] = {
    "trip_id": "trip-exemplo-001",
    "title": "Roteiro Teresina a Piripiri",
    "origin": "Teresina - PI",
    "destination": "Piripiri - PI",
    "distance_km": 165.4,
    "duration_min": 140.0,
    "summary": "Viagem cultural e de ecoturismo pelo norte do Piauí.",
    "days": [
        {
            "day": 1,
            "activities": [
                {
                    "time": "09:00",
                    "title": "Parque Nacional de Sete Cidades",
                    "description": "Trilha guiada pelas formações rochosas e pinturas rupestres.",
                }
            ],
        }
    ],
    "map_url": "https://www.google.com/maps/dir/?api=1&origin=Teresina-PI&destination=Piripiri-PI",
}

DISPATCH_EVENT_EXAMPLE: dict[str, Any] = {
    "event_type": "turismo.roteiro.despachar",
    "event_id": "3f2504e0-4f89-41d3-9a0c-0305e82c3301",
    "occurred_at": "2026-11-19T18:35:00Z",
    "trace_id": "b1c2d3e4f5a64b7c8d9e0f1a2b3c4d5e",
    "channel": "email",
    "recipient": {
        "name": "Viajante Exemplo",
        "email": "viajante@example.com",
    },
    "language": "pt-BR",
    "itinerary": ITINERARY_EXAMPLE,
}

WEATHER_REQUEST_EXAMPLE: dict[str, Any] = {
    "trace_id": "c1d2e3f4a5b64c7d8e9f0a1b2c3d4e5f",
    "latitude": -5.0892,
    "longitude": -42.8019,
    "start_date": "2026-11-26",
    "end_date": "2026-11-28",
    "language": "pt-BR",
}

WEATHER_RESPONSE_EXAMPLE: dict[str, Any] = {
    "days": [
        {
            "date": "2026-11-26",
            "temp_min_c": 24.0,
            "temp_max_c": 36.2,
            "precipitation_probability": 20,
            "alert": "heat",
        }
    ],
    "guidance": "Leve água e protetor solar; prefira atividades externas no início da manhã.",
    "source": "open-meteo",
}


class DlqRequestInfo(BaseModel):
    """Resumo seguro da requisição que gerou a falha (sem dados pessoais)."""

    model_config = ConfigDict(extra="forbid")

    method: str
    route: str
    status_code: int
    language: str | None = None


class DlqErrorInfo(BaseModel):
    """Detalhes técnicos truncados da exceção para o alerta da equipe."""

    model_config = ConfigDict(extra="forbid")

    type: str
    message: str = Field(max_length=500)
    stack_trace: str = Field(max_length=3000)


class DlqEvent(BaseModel):
    """Espelho de specs/003-integracao-eda-n8n/contracts/dlq-event.schema.json."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [DLQ_EVENT_EXAMPLE]},
    )

    event_type: Literal["turismo.falha"] = "turismo.falha"
    event_id: UUID
    occurred_at: datetime
    trace_id: str
    environment: Literal["local", "staging", "production"]
    is_test: bool = False
    request: DlqRequestInfo
    error: DlqErrorInfo


class Recipient(BaseModel):
    """Destinatário do despacho do roteiro."""

    model_config = ConfigDict(extra="forbid")

    name: str
    email: EmailStr | None = None
    phone: str | None = Field(default=None, pattern=r"^\+[1-9][0-9]{7,14}$")


class ItineraryActivity(BaseModel):
    """Atividade de um dia do roteiro."""

    time: str | None = None
    title: str
    description: str | None = None


class ItineraryDay(BaseModel):
    """Dia de um roteiro estruturado."""

    day: int = Field(ge=1)
    activities: list[ItineraryActivity]


class Itinerary(BaseModel):
    """Roteiro estruturado usado no chat (P4) e no despacho (P5)."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [ITINERARY_EXAMPLE]},
    )

    trip_id: str
    title: str
    origin: str
    destination: str
    distance_km: float | None = None
    duration_min: float | None = None
    summary: str | None = None
    days: list[ItineraryDay] = Field(min_length=1)
    map_url: HttpUrl | None = None


class DispatchEvent(BaseModel):
    """Espelho de specs/003-integracao-eda-n8n/contracts/dispatch-event.schema.json."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [DISPATCH_EVENT_EXAMPLE]},
    )

    event_type: Literal["turismo.roteiro.despachar"] = "turismo.roteiro.despachar"
    event_id: UUID
    occurred_at: datetime
    trace_id: str
    channel: Literal["email", "whatsapp"]
    recipient: Recipient
    language: str
    itinerary: Itinerary

    @model_validator(mode="after")
    def validate_recipient_for_channel(self) -> DispatchEvent:
        if self.channel == "email" and not self.recipient.email:
            raise ValueError("recipient.email é obrigatório quando channel='email'.")
        if self.channel == "whatsapp" and not self.recipient.phone:
            raise ValueError("recipient.phone é obrigatório quando channel='whatsapp'.")
        return self


class WeatherRequest(BaseModel):
    """Espelho de $defs.request em weather-webhook.schema.json."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [WEATHER_REQUEST_EXAMPLE]},
    )

    trace_id: str
    latitude: float = Field(ge=-34, le=6)
    longitude: float = Field(ge=-74, le=-34)
    start_date: CalendarDate
    end_date: CalendarDate
    language: str


class WeatherDay(BaseModel):
    """Previsão diária retornada pelo webhook turismo-clima."""

    date: CalendarDate
    temp_min_c: float
    temp_max_c: float
    precipitation_probability: int = Field(ge=0, le=100)
    alert: Literal["none", "rain", "heat", "rain_and_heat"] | None = None


class WeatherResponse(BaseModel):
    """Espelho de $defs.response em weather-webhook.schema.json."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [WEATHER_RESPONSE_EXAMPLE]},
    )

    days: list[WeatherDay]
    guidance: str
    source: Literal["open-meteo"] = "open-meteo"
