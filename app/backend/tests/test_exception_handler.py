"""Testes do handler global de exceções e integração assíncrona com a DLQ (issue #2 / T0006)."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Generator
from time import perf_counter
from typing import Any

import httpx
import jsonschema
import pytest
import respx
from fastapi import APIRouter
from fastapi.testclient import TestClient
from starlette.types import Message

from app.core.config import REPOSITORY_ROOT, get_settings
from app.core.dependencies import get_current_user
from app.main import app
from app.routers import trips as trips_router
from app.schemas.events import DLQ_EVENT_EXAMPLE
from app.services import events as events_service
from app.services.events import (
    limpar_cache_ssl_n8n,
    publicar_evento,
    resetar_total_eventos_dlq,
)

DLQ_SCHEMA_PATH = (
    REPOSITORY_ROOT
    / "specs"
    / "003-integracao-eda-n8n"
    / "contracts"
    / "dlq-event.schema.json"
)


def _carregar_schema_dlq() -> dict[str, Any]:
    return dict(json.loads(DLQ_SCHEMA_PATH.read_text(encoding="utf-8")))


@pytest.fixture(autouse=True)
def _isolamento_config_e_contador() -> Generator[None, None, None]:
    get_settings.cache_clear()
    resetar_total_eventos_dlq()
    yield
    get_settings.cache_clear()
    resetar_total_eventos_dlq()
    limpar_cache_ssl_n8n()


@pytest.fixture
def rota_falha_registrada() -> Generator[str, None, None]:
    """Registra rota temporária com parâmetro de caminho e restaura ``app.router.routes``."""
    rotas_originais = list(app.router.routes)
    router_temp = APIRouter(prefix="/api/v1/roteiros")

    @router_temp.post("/{trip_id}/falha-simulada-teste")
    async def _rota_com_excecao(trip_id: str) -> dict[str, str]:
        raise RuntimeError("Falha interna simulada no serviço")

    app.include_router(router_temp)
    app.openapi_schema = None
    try:
        yield "/api/v1/roteiros/{trip_id}/falha-simulada-teste"
    finally:
        app.router.routes[:] = rotas_originais
        app.openapi_schema = None


def test_excecao_nao_tratada_retorna_500_minimo_cabecalhos_e_evento_sem_pii(
    monkeypatch: pytest.MonkeyPatch,
    rota_falha_registrada: str,
) -> None:
    monkeypatch.setenv("N8N_WEBHOOK_BASE_URL", "https://n8n.exemplo.test/webhook")
    monkeypatch.setenv("N8N_WEBHOOK_SECRET", "segredo-webhook")
    monkeypatch.setenv("APP_ENV", "local")
    get_settings.cache_clear()

    with (
        respx.mock(assert_all_called=True) as router,
        TestClient(app, raise_server_exceptions=False) as client,
    ):
        rota_n8n = router.post("https://n8n.exemplo.test/webhook/turismo-dlq").mock(
            return_value=httpx.Response(202)
        )
        resposta = client.post(
            "/api/v1/roteiros/viagem-privada-999/falha-simulada-teste?email=ana@exemplo.com",
            headers={
                "X-Request-ID": "trace-custom-12345",
                "Accept-Language": "fr",
                "Authorization": "Bearer token-super-confidencial",
                "Cookie": "guia_turista_session=cookie-secreto-xyz",
                "Origin": "http://localhost:5173",
            },
            json={
                "email": "ana@exemplo.com",
                "nome": "Ana Viajante",
                "foto": "https://cdn.exemplo.com/avatar-ana.jpg",
            },
        )

    assert resposta.status_code == 500
    corpo = resposta.json()
    assert set(corpo.keys()) == {"detail", "trace_id"}
    assert corpo["detail"] == "Algo deu errado. Informe o código ao suporte."
    assert corpo["trace_id"] == "trace-custom-12345"
    assert resposta.headers["X-Request-ID"] == "trace-custom-12345"
    assert resposta.headers["X-Process-Time"].endswith("ms")
    assert resposta.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"

    assert rota_n8n.call_count == 1
    payload = json.loads(rota_n8n.calls.last.request.content)
    jsonschema.validate(
        instance=payload,
        schema=_carregar_schema_dlq(),
        format_checker=jsonschema.FormatChecker(),
    )
    assert payload["trace_id"] == "trace-custom-12345"
    assert payload["is_test"] is False
    assert payload["request"] == {
        "method": "POST",
        "route": rota_falha_registrada,
        "status_code": 500,
        "language": "fr",
    }

    texto_payload = json.dumps(payload)
    for dado_proibido in (
        "ana@exemplo.com",
        "Ana Viajante",
        "avatar-ana.jpg",
        "viagem-privada-999",
        "token-super-confidencial",
        "cookie-secreto-xyz",
    ):
        assert dado_proibido not in texto_payload


@pytest.mark.asyncio
async def test_resposta_500_nao_espera_n8n_lento_e_loga_apos_resposta(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    rota_falha_registrada: str,
) -> None:
    monkeypatch.setenv("N8N_WEBHOOK_BASE_URL", "https://n8n.exemplo.test/webhook")
    monkeypatch.setenv("N8N_WEBHOOK_SECRET", "segredo-webhook")
    monkeypatch.setenv("N8N_TIMEOUT_SECONDS", "10")
    get_settings.cache_clear()

    resposta_entregue = asyncio.Event()
    mensagens_enviadas: list[dict[str, Any]] = []
    requisicao_lida = False
    entregue_em: float | None = None
    n8n_concluido_em: float | None = None

    async def atraso_n8n(_request: httpx.Request) -> httpx.Response:
        nonlocal n8n_concluido_em
        await asyncio.sleep(5.0)
        n8n_concluido_em = perf_counter()
        return httpx.Response(202, json={"message": "Workflow was started"})

    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/v1/roteiros/abc/falha-simulada-teste",
        "raw_path": b"/api/v1/roteiros/abc/falha-simulada-teste",
        "query_string": b"",
        "headers": [(b"accept-language", b"en")],
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
    }

    async def receive() -> dict[str, Any]:
        nonlocal requisicao_lida
        if not requisicao_lida:
            requisicao_lida = True
            return {"type": "http.request", "body": b"{}", "more_body": False}
        await asyncio.Event().wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        nonlocal entregue_em
        mensagens_enviadas.append(dict(message))
        if message["type"] == "http.response.body" and not message.get(
            "more_body", False
        ):
            entregue_em = perf_counter()
            resposta_entregue.set()

    with (
        respx.mock(assert_all_called=True) as router,
        caplog.at_level("INFO", logger="app.services.events"),
    ):
        router.post("https://n8n.exemplo.test/webhook/turismo-dlq").mock(
            side_effect=atraso_n8n
        )

        inicio = perf_counter()
        tarefa_asgi = asyncio.create_task(app(scope, receive, send))

        await asyncio.wait_for(resposta_entregue.wait(), timeout=1.0)
        latencia_despertar = perf_counter() - inicio
        assert entregue_em is not None
        latencia_entrega = entregue_em - inicio

        # Tanto a entrega real do body HTTP 500 quanto o retorno do controle ao
        # event loop ocorrem em < 1 s, enquanto o envio de 5 s ao n8n segue ativo.
        assert latencia_entrega < 1.0
        assert latencia_despertar < 1.0
        assert "evento enviado ao n8n" not in caplog.text

        with pytest.raises(RuntimeError, match="Falha interna simulada"):
            await tarefa_asgi

    assert n8n_concluido_em is not None
    assert n8n_concluido_em - entregue_em >= 4.0
    inicio_msg = next(m for m in mensagens_enviadas if m["type"] == "http.response.start")
    corpo_msg = next(m for m in mensagens_enviadas if m["type"] == "http.response.body")
    assert inicio_msg["status"] == 500
    corpo_json = json.loads(corpo_msg["body"].decode("utf-8"))
    assert set(corpo_json.keys()) == {"detail", "trace_id"}
    assert "evento enviado ao n8n" in caplog.text


@pytest.mark.asyncio
async def test_publicar_evento_reutiliza_ssl_context_e_nao_bloqueia_event_loop_no_cold_load(
    monkeypatch: pytest.MonkeyPatch,
    rota_falha_registrada: str,
) -> None:
    """Regressão #39: carga fria lenta de certificados CA roda fora do event loop e é cacheada."""
    monkeypatch.setenv("N8N_WEBHOOK_BASE_URL", "https://n8n.exemplo.test/webhook")
    monkeypatch.setenv("N8N_WEBHOOK_SECRET", "segredo-webhook")
    monkeypatch.setenv("N8N_TIMEOUT_SECONDS", "10")
    get_settings.cache_clear()
    limpar_cache_ssl_n8n()

    criacoes_ssl = 0
    criar_real = httpx.create_ssl_context

    def criar_ssl_lento(*args: Any, **kwargs: Any) -> Any:
        nonlocal criacoes_ssl
        criacoes_ssl += 1
        time.sleep(1.65)
        return criar_real(*args, **kwargs)

    monkeypatch.setattr(events_service.httpx, "create_ssl_context", criar_ssl_lento)

    resposta_entregue = asyncio.Event()
    requisicao_lida = False

    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/v1/roteiros/abc/falha-simulada-teste",
        "raw_path": b"/api/v1/roteiros/abc/falha-simulada-teste",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 50000),
        "server": ("testserver", 80),
    }

    async def receive() -> dict[str, Any]:
        nonlocal requisicao_lida
        if not requisicao_lida:
            requisicao_lida = True
            return {"type": "http.request", "body": b"{}", "more_body": False}
        await asyncio.Event().wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        if message["type"] == "http.response.body" and not message.get(
            "more_body", False
        ):
            resposta_entregue.set()

    with respx.mock(assert_all_called=True) as router:
        rota_n8n = router.post(
            "https://n8n.exemplo.test/webhook/turismo-dlq"
        ).mock(return_value=httpx.Response(202))

        inicio = perf_counter()
        tarefa_asgi = asyncio.create_task(app(scope, receive, send))

        # Mesmo com create_ssl_context bloqueando 1,65 s (cenário reproduzido na #39),
        # o event loop acorda imediatamente (< 250 ms) graças ao run_in_threadpool.
        await asyncio.wait_for(resposta_entregue.wait(), timeout=0.5)
        latencia_despertar = perf_counter() - inicio
        assert latencia_despertar < 0.5

        with pytest.raises(RuntimeError, match="Falha interna simulada"):
            await tarefa_asgi

        # Segunda chamada reutiliza o SSLContext em cache sem recarregar CA.
        await publicar_evento("turismo-dlq", DLQ_EVENT_EXAMPLE)

    assert criacoes_ssl == 1
    assert rota_n8n.call_count == 2


@pytest.mark.parametrize(
    "falha_n8n",
    [
        httpx.Response(500, text="Internal Server Error"),
        httpx.ReadTimeout("n8n lento demais"),
    ],
)
def test_falha_do_n8n_nao_altera_resposta_500_ao_usuario(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    rota_falha_registrada: str,
    falha_n8n: httpx.Response | Exception,
) -> None:
    monkeypatch.setenv("N8N_WEBHOOK_BASE_URL", "https://n8n.exemplo.test/webhook")
    monkeypatch.setenv("N8N_WEBHOOK_SECRET", "segredo-webhook")
    get_settings.cache_clear()

    with (
        respx.mock(assert_all_called=True) as router,
        TestClient(app, raise_server_exceptions=False) as client,
    ):
        if isinstance(falha_n8n, httpx.Response):
            router.post("https://n8n.exemplo.test/webhook/turismo-dlq").mock(
                return_value=falha_n8n
            )
        else:
            router.post("https://n8n.exemplo.test/webhook/turismo-dlq").mock(
                side_effect=falha_n8n
            )

        with caplog.at_level("ERROR", logger="app.services.events"):
            resposta = client.post("/api/v1/roteiros/123/falha-simulada-teste")

    assert resposta.status_code == 500
    corpo = resposta.json()
    assert set(corpo.keys()) == {"detail", "trace_id"}
    assert resposta.headers["X-Request-ID"] == corpo["trace_id"]
    assert "falha ao publicar evento no n8n" in caplog.text


def test_falha_em_persist_trip_dispara_dlq_sem_quebrar_planejamento(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("N8N_WEBHOOK_BASE_URL", "https://n8n.exemplo.test/webhook")
    monkeypatch.setenv("N8N_WEBHOOK_SECRET", "segredo-webhook")
    get_settings.cache_clear()

    viagem_fake: dict[str, Any] = {
        "id": "trip-teste-dlq",
        "origem_formatada": "Teresina - PI",
        "destino_formatada": "Piripiri - PI",
        "distancia_km": 165.0,
        "duracao_minutos": 140.0,
        "combustivel_litros": 15.0,
        "custo_combustivel": 90.0,
        "pedagio_estimado": 0.0,
        "custo_total_estimado": 90.0,
        "geometria_rota": [[-5.0892, -42.8019], [-4.2719, -41.7769]],
        "alternativas_rota": [],
        "postos_combustivel": [],
        "atrativos": [],
        "perfil_altimetrico": [],
        "clima_destino": {},
        "guia_turistico": "Guia válido.",
        "criado_em": "2026-11-26T00:00:00Z",
    }

    async def _plan_trip_fake(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return dict(viagem_fake)

    def _persist_quebrado(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("Falha simulada ao gravar viagens.json")

    monkeypatch.setattr(trips_router, "plan_trip", _plan_trip_fake)
    monkeypatch.setattr(trips_router, "persist_trip", _persist_quebrado)
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "usr-teste-dlq",
        "tipo": "google",
        "email": "privado@exemplo.com",
        "nome": "Viajante Privado",
    }

    try:
        with (
            respx.mock(assert_all_called=True) as router,
            TestClient(app) as client,
        ):
            rota_n8n = router.post(
                "https://n8n.exemplo.test/webhook/turismo-dlq"
            ).mock(return_value=httpx.Response(202))

            resposta = client.post(
                "/api/v1/roteiros/planejar",
                headers={
                    "X-Request-ID": "trace-persist-dlq",
                    "Accept-Language": "es",
                },
                json={
                    "origem_cidade": "Teresina",
                    "origem_uf": "PI",
                    "destino_cidade": "Piripiri",
                    "destino_uf": "PI",
                },
            )
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        trips_router._recent_requests.clear()
        trips_router._active_requests.clear()

    assert resposta.status_code == 200
    assert rota_n8n.call_count == 1
    payload = json.loads(rota_n8n.calls.last.request.content)
    jsonschema.validate(
        instance=payload,
        schema=_carregar_schema_dlq(),
        format_checker=jsonschema.FormatChecker(),
    )
    assert payload["trace_id"] == "trace-persist-dlq"
    assert payload["request"] == {
        "method": "POST",
        "route": "/api/v1/roteiros/planejar",
        "status_code": 500,
        "language": "es",
    }
    assert "privado@exemplo.com" not in json.dumps(payload)
