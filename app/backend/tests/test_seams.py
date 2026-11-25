"""Testes de contrato e fumaça dos pontos de encaixe compartilhados do PR 0 (#18)."""

import json
import logging
from typing import Any

import jsonschema
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import REPOSITORY_ROOT, Settings
from app.main import app
from app.routers import chat, despacho, postos, suporte
from app.schemas.events import (
    DISPATCH_EVENT_EXAMPLE,
    DLQ_EVENT_EXAMPLE,
    WEATHER_REQUEST_EXAMPLE,
    WEATHER_RESPONSE_EXAMPLE,
    DispatchEvent,
    DlqEvent,
    Itinerary,
    WeatherRequest,
    WeatherResponse,
)
from app.services.events import publicar_evento

CONTRACTS_DIR = REPOSITORY_ROOT / "specs" / "003-integracao-eda-n8n" / "contracts"


def _load_schema(filename: str) -> dict[str, Any]:
    return dict(json.loads((CONTRACTS_DIR / filename).read_text(encoding="utf-8")))


def test_settings_boots_without_spec_003_env_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for var in (
        "N8N_WEBHOOK_BASE_URL",
        "N8N_WEBHOOK_SECRET",
        "N8N_TIMEOUT_SECONDS",
        "SUPPORT_API_KEY",
        "APP_ENV",
    ):
        monkeypatch.delenv(var, raising=False)

    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.n8n_webhook_base_url == ""
    assert settings.n8n_webhook_secret == ""
    assert settings.n8n_timeout_seconds == 3.0
    assert settings.support_api_key == ""
    assert settings.app_env == "local"


def test_env_example_declares_spec_003_variables_without_secrets() -> None:
    content = (REPOSITORY_ROOT / ".env.example").read_text(encoding="utf-8")
    for expected_line in (
        'N8N_WEBHOOK_BASE_URL=""',
        'N8N_WEBHOOK_SECRET=""',
        "N8N_TIMEOUT_SECONDS=3",
        'SUPPORT_API_KEY=""',
        'APP_ENV="local"',
    ):
        assert expected_line in content


def test_new_routers_have_fixed_prefixes_and_appear_in_docs() -> None:
    assert suporte.router.prefix == "/api/v1/suporte"
    assert postos.router.prefix == "/api/v1/postos"
    assert chat.router.prefix == "/api/v1/chat"
    assert despacho.router.prefix == "/api/v1/despacho"

    with TestClient(app) as client:
        openapi_resp = client.get("/openapi.json")
        docs_resp = client.get("/docs")

    assert openapi_resp.status_code == 200
    assert docs_resp.status_code == 200
    tag_names = {tag["name"] for tag in openapi_resp.json().get("tags", [])}
    assert {"suporte", "postos", "chat", "despacho"}.issubset(tag_names)


def test_dlq_event_model_matches_json_schema() -> None:
    schema = _load_schema("dlq-event.schema.json")
    model = DlqEvent.model_validate(DLQ_EVENT_EXAMPLE)
    payload = model.model_dump(mode="json", exclude_none=True)
    jsonschema.validate(
        instance=payload,
        schema=schema,
        format_checker=jsonschema.FormatChecker(),
    )


def test_dispatch_event_and_itinerary_match_json_schema() -> None:
    schema = _load_schema("dispatch-event.schema.json")
    model = DispatchEvent.model_validate(DISPATCH_EVENT_EXAMPLE)
    assert isinstance(model.itinerary, Itinerary)
    payload = model.model_dump(mode="json", exclude_none=True)
    jsonschema.validate(
        instance=payload,
        schema=schema,
        format_checker=jsonschema.FormatChecker(),
    )

    whatsapp_event = DispatchEvent.model_validate(
        {
            **DISPATCH_EVENT_EXAMPLE,
            "channel": "whatsapp",
            "recipient": {"name": "Viajante Exemplo", "phone": "+5586999999999"},
        }
    )
    jsonschema.validate(
        instance=whatsapp_event.model_dump(mode="json", exclude_none=True),
        schema=schema,
        format_checker=jsonschema.FormatChecker(),
    )

    with pytest.raises(ValidationError):
        DispatchEvent.model_validate(
            {
                **DISPATCH_EVENT_EXAMPLE,
                "channel": "whatsapp",
                "recipient": {"name": "Sem Telefone", "email": "a@example.com"},
            }
        )


def test_weather_models_match_json_schema() -> None:
    schema = _load_schema("weather-webhook.schema.json")

    req_payload = WeatherRequest.model_validate(WEATHER_REQUEST_EXAMPLE).model_dump(
        mode="json", exclude_none=True
    )
    jsonschema.validate(
        instance=req_payload,
        schema=schema["$defs"]["request"],
        format_checker=jsonschema.FormatChecker(),
    )

    resp_payload = WeatherResponse.model_validate(WEATHER_RESPONSE_EXAMPLE).model_dump(
        mode="json", exclude_none=True
    )
    jsonschema.validate(
        instance=resp_payload,
        schema=schema["$defs"]["response"],
        format_checker=jsonschema.FormatChecker(),
    )


@pytest.mark.asyncio
async def test_publicar_evento_stub_accepts_fixed_signature(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("INFO", logger="app.services.events"):
        await publicar_evento("turismo-dlq", DLQ_EVENT_EXAMPLE)
    assert "turismo-dlq" in caplog.text


def test_logging_scopes_info_to_app_and_suppresses_httpx() -> None:
    assert logging.getLogger("app").getEffectiveLevel() == logging.INFO
    assert logging.getLogger("app.services.events").getEffectiveLevel() == logging.INFO
    assert logging.getLogger("httpx").getEffectiveLevel() == logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() == logging.WARNING
