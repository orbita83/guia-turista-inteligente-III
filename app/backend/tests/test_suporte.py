"""Testes de autenticação, contrato OpenAPI e métricas reais de suporte (#4 / T0007 — 4a + 4b)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Generator
from datetime import UTC, datetime
from time import monotonic, perf_counter
from typing import Any

import httpx
import jsonschema
import pytest
import respx
import yaml  # type: ignore[import-untyped]
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.types import Message

from app.core.circuit_breaker import CircuitState
from app.core.config import REPOSITORY_ROOT, get_settings
from app.main import app
from app.routers import suporte as suporte_router
from app.services.events import resetar_total_eventos_dlq

CONTRACTS_DIR = REPOSITORY_ROOT / "specs" / "003-integracao-eda-n8n" / "contracts"
CHAVE_VALIDA = "sup_chave_teste_chatops_32_caracteres_ok"


@pytest.fixture(autouse=True)
def _limpar_estado_suporte() -> Generator[None, None, None]:
    get_settings.cache_clear()
    resetar_total_eventos_dlq()
    yield
    get_settings.cache_clear()
    resetar_total_eventos_dlq()


def _carregar_openapi_suporte() -> dict[str, Any]:
    conteudo = (CONTRACTS_DIR / "support-api.yaml").read_text(encoding="utf-8")
    return dict(yaml.safe_load(conteudo))


def _carregar_schema_dlq() -> dict[str, Any]:
    conteudo = (CONTRACTS_DIR / "dlq-event.schema.json").read_text(encoding="utf-8")
    return dict(json.loads(conteudo))


def _schema_resposta(
    spec: dict[str, Any], path: str, method: str, code: str
) -> dict[str, Any]:
    return dict(
        spec["paths"][path][method]["responses"][code]["content"]["application/json"][
            "schema"
        ]
    )


def test_support_api_key_vazia_retorna_503_mesmo_com_cabecalho_vazio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPPORT_API_KEY", "")
    get_settings.cache_clear()

    with TestClient(app) as client:
        sem_header = client.get("/api/v1/suporte/status")
        com_header_vazio = client.get(
            "/api/v1/suporte/status",
            headers={"X-Support-Key": ""},
        )
        com_header_qualquer = client.post(
            "/api/v1/suporte/testardlq",
            headers={"X-Support-Key": "qualquer-valor"},
        )

    assert sem_header.status_code == 503
    assert com_header_vazio.status_code == 503
    assert com_header_qualquer.status_code == 503


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"X-Support-Key": ""},
        {"X-Support-Key": "chave-incorreta"},
        {"X-Support-Key": "cháve-não-ascii-🚀-inválida".encode()},
    ],
)
def test_chave_ausente_errada_ou_nao_ascii_retorna_401_sem_vazar_segredo(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    headers: dict[str, str | bytes],
) -> None:
    monkeypatch.setenv("SUPPORT_API_KEY", CHAVE_VALIDA)
    get_settings.cache_clear()

    spec = _carregar_openapi_suporte()
    unauthorized_schema = spec["components"]["responses"]["Unauthorized"]["content"][
        "application/json"
    ]["schema"]

    with caplog.at_level("INFO"), TestClient(app) as client:
        resposta = client.get("/api/v1/suporte/status", headers=headers)  # type: ignore[arg-type]

    assert resposta.status_code == 401
    corpo = resposta.json()
    jsonschema.validate(instance=corpo, schema=unauthorized_schema)
    assert corpo == {"detail": "Não autorizado."}
    assert CHAVE_VALIDA not in caplog.text
    valor_header = headers.get("X-Support-Key")
    if isinstance(valor_header, str) and valor_header:
        assert valor_header not in caplog.text


def test_todas_as_rotas_do_router_suporte_exigem_chave_valida(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPPORT_API_KEY", CHAVE_VALIDA)
    get_settings.cache_clear()

    rotas_http = [
        rota for rota in suporte_router.router.routes if isinstance(rota, APIRoute)
    ]
    assert len(rotas_http) >= 4

    with TestClient(app) as client:
        for rota in rotas_http:
            metodos = [
                m for m in (rota.methods or set()) if m not in {"HEAD", "OPTIONS"}
            ]
            assert metodos, f"Rota {rota.path} sem métodos HTTP testáveis"
            for metodo in metodos:
                sem_chave = client.request(metodo, rota.path)
                chave_errada = client.request(
                    metodo,
                    rota.path,
                    headers={"X-Support-Key": "chave-errada"},
                )
                assert (
                    sem_chave.status_code == 401
                ), f"{metodo} {rota.path} aceitou sem chave"
                assert (
                    chave_errada.status_code == 401
                ), f"{metodo} {rota.path} aceitou chave inválida"


def test_respostas_reais_validam_contra_support_api_yaml_e_refletem_breakers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPPORT_API_KEY", CHAVE_VALIDA)
    monkeypatch.setenv("N8N_WEBHOOK_BASE_URL", "https://n8n.exemplo.test/webhook")
    monkeypatch.setenv("N8N_WEBHOOK_SECRET", "segredo-dlq")
    get_settings.cache_clear()

    spec = _carregar_openapi_suporte()
    headers = {"X-Support-Key": CHAVE_VALIDA, "X-Request-ID": "req-suporte-abc123"}

    with (
        respx.mock(assert_all_called=True) as router_n8n,
        TestClient(app) as client,
    ):
        rota_dlq = router_n8n.post(
            "https://n8n.exemplo.test/webhook/turismo-dlq"
        ).mock(return_value=httpx.Response(202))

        # Uptime simulado de 2h 14min (8040s)
        client.app.state.started_at = monotonic() - 8040.4  # type: ignore[attr-defined]
        client.app.state.started_at_utc = datetime(2026, 11, 26, 0, 0, tzinfo=UTC)  # type: ignore[attr-defined]

        resp_status_ok = client.get("/api/v1/suporte/status", headers=headers)
        resp_uptime = client.get("/api/v1/suporte/uptime", headers=headers)
        resp_dlq = client.post("/api/v1/suporte/testardlq", headers=headers)
        resp_telemetria = client.get("/api/v1/suporte/telemetria", headers=headers)

        # Degrada o breaker weather e valida transição de status -> degraded
        breakers = client.app.state.circuit_breakers  # type: ignore[attr-defined]
        breakers["weather"].state = CircuitState.OPEN
        resp_status_degraded = client.get("/api/v1/suporte/status", headers=headers)

    assert resp_status_ok.status_code == 200
    assert resp_status_degraded.status_code == 200
    assert resp_uptime.status_code == 200
    assert resp_telemetria.status_code == 200
    assert resp_dlq.status_code == 202
    assert rota_dlq.call_count == 1

    checker = jsonschema.FormatChecker()
    jsonschema.validate(
        resp_status_ok.json(),
        _schema_resposta(spec, "/api/v1/suporte/status", "get", "200"),
        format_checker=checker,
    )
    jsonschema.validate(
        resp_status_degraded.json(),
        _schema_resposta(spec, "/api/v1/suporte/status", "get", "200"),
        format_checker=checker,
    )
    jsonschema.validate(
        resp_uptime.json(),
        _schema_resposta(spec, "/api/v1/suporte/uptime", "get", "200"),
        format_checker=checker,
    )
    jsonschema.validate(
        resp_telemetria.json(),
        _schema_resposta(spec, "/api/v1/suporte/telemetria", "get", "200"),
        format_checker=checker,
    )
    jsonschema.validate(
        resp_dlq.json(),
        _schema_resposta(spec, "/api/v1/suporte/testardlq", "post", "202"),
        format_checker=checker,
    )

    assert resp_status_ok.json()["status"] == "ok"
    assert [d["name"] for d in resp_status_ok.json()["dependencies"]] == [
        "weather",
        "guide",
    ]
    assert resp_status_degraded.json()["status"] == "degraded"

    uptime_json = resp_uptime.json()
    assert uptime_json["started_at"] == "2026-11-26T00:00:00Z"
    assert uptime_json["uptime_seconds"] >= 8040
    assert uptime_json["uptime_human"] == "2h 14min"

    telemetria_json = resp_telemetria.json()
    assert telemetria_json["requests_total"] >= 3
    assert telemetria_json["in_flight"] >= 1
    assert telemetria_json["dlq_events_total"] == 1
    assert isinstance(telemetria_json["latency_p95_ms"], float)

    assert resp_dlq.json() == {"trace_id": "req-suporte-abc123", "scheduled": True}
    assert resp_dlq.headers["X-Request-ID"] == "req-suporte-abc123"


def test_status_retorna_down_quando_app_state_nao_inicializado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPPORT_API_KEY", CHAVE_VALIDA)
    get_settings.cache_clear()

    app_sem_lifespan = FastAPI()
    app_sem_lifespan.include_router(suporte_router.router)

    client = TestClient(app_sem_lifespan)
    resposta = client.get(
        "/api/v1/suporte/status",
        headers={"X-Support-Key": CHAVE_VALIDA},
    )
    assert resposta.status_code == 200
    assert resposta.json()["status"] == "down"
    assert resposta.json()["dependencies"] == []


def test_cors_nao_autoriza_cabecalho_x_support_key() -> None:
    with TestClient(app) as client:
        preflight = client.options(
            "/api/v1/suporte/status",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "X-Support-Key",
            },
        )

    allow_headers = preflight.headers.get("access-control-allow-headers", "").lower()
    assert "x-support-key" not in allow_headers


@pytest.mark.asyncio
async def test_testardlq_agenda_evento_valido_sem_esperar_publicador_lento(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SUPPORT_API_KEY", CHAVE_VALIDA)
    get_settings.cache_clear()

    chamadas: list[tuple[str, dict[str, Any]]] = []
    resposta_entregue = asyncio.Event()
    mensagens: list[dict[str, Any]] = []
    requisicao_lida = False

    async def publicador_lento(webhook_path: str, payload: dict[str, Any]) -> None:
        await asyncio.sleep(2.0)
        chamadas.append((webhook_path, payload))

    monkeypatch.setattr(suporte_router, "publicar_evento", publicador_lento)

    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/v1/suporte/testardlq",
        "raw_path": b"/api/v1/suporte/testardlq",
        "query_string": b"",
        "headers": [
            (b"x-support-key", CHAVE_VALIDA.encode("utf-8")),
            (b"x-request-id", b"trace-testardlq-001"),
            (b"accept-language", b"en"),
        ],
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
    }

    async def receive() -> dict[str, Any]:
        nonlocal requisicao_lida
        if not requisicao_lida:
            requisicao_lida = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await asyncio.Event().wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        mensagens.append(dict(message))
        if message["type"] == "http.response.body" and not message.get(
            "more_body", False
        ):
            resposta_entregue.set()

    inicio = perf_counter()
    tarefa = asyncio.create_task(app(scope, receive, send))
    await asyncio.wait_for(resposta_entregue.wait(), timeout=0.8)
    latencia = perf_counter() - inicio

    assert latencia < 0.8
    assert not chamadas
    await tarefa

    assert len(chamadas) == 1
    caminho, payload = chamadas[0]
    assert caminho == "turismo-dlq"
    jsonschema.validate(
        instance=payload,
        schema=_carregar_schema_dlq(),
        format_checker=jsonschema.FormatChecker(),
    )
    assert payload["is_test"] is True
    assert payload["trace_id"] == "trace-testardlq-001"
    assert payload["request"] == {
        "method": "POST",
        "route": "/api/v1/suporte/testardlq",
        "status_code": 500,
        "language": "en",
    }
