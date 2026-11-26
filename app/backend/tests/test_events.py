"""Testes unitários e de contrato do publicador assíncrono de eventos (issue #2 / T0006)."""

from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

import httpx
import jsonschema
import pytest
import respx

from app.core.config import REPOSITORY_ROOT, get_settings
from app.schemas.events import DLQ_EVENT_EXAMPLE
from app.services.events import (
    construir_evento_dlq,
    executar_tarefa_com_dlq,
    obter_total_eventos_dlq,
    publicar_evento,
    resetar_total_eventos_dlq,
    resolver_idioma_seguro,
)

DLQ_SCHEMA_PATH = (
    REPOSITORY_ROOT
    / "specs"
    / "003-integracao-eda-n8n"
    / "contracts"
    / "dlq-event.schema.json"
)


@pytest.fixture(autouse=True)
def _limpar_estado_eventos() -> Generator[None, None, None]:
    get_settings.cache_clear()
    resetar_total_eventos_dlq()
    yield
    get_settings.cache_clear()
    resetar_total_eventos_dlq()


def _carregar_schema_dlq() -> dict[str, Any]:
    return dict(json.loads(DLQ_SCHEMA_PATH.read_text(encoding="utf-8")))


@pytest.mark.asyncio
async def test_publicar_evento_sem_url_apenas_loga_sem_rede(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("N8N_WEBHOOK_BASE_URL", "")
    monkeypatch.setenv("N8N_WEBHOOK_SECRET", "segredo-super-secreto")
    get_settings.cache_clear()

    with respx.mock(assert_all_called=False) as router:
        rota = router.post(url__regex=r".*")
        with caplog.at_level("INFO", logger="app.services.events"):
            await publicar_evento("turismo-dlq", DLQ_EVENT_EXAMPLE)

    assert not rota.called
    assert obter_total_eventos_dlq() == 0
    assert "Modo local" in caplog.text
    assert DLQ_EVENT_EXAMPLE["event_id"] in caplog.text
    assert DLQ_EVENT_EXAMPLE["trace_id"] in caplog.text
    assert "segredo-super-secreto" not in caplog.text


@pytest.mark.asyncio
async def test_publicar_evento_envia_post_com_segredo_e_incrementa_contador(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("N8N_WEBHOOK_BASE_URL", "https://n8n.exemplo.test/webhook/")
    monkeypatch.setenv("N8N_WEBHOOK_SECRET", "chave-n8n-teste")
    monkeypatch.setenv("N8N_TIMEOUT_SECONDS", "3")
    get_settings.cache_clear()

    with respx.mock(assert_all_called=True) as router:
        rota = router.post("https://n8n.exemplo.test/webhook/turismo-dlq").mock(
            return_value=httpx.Response(202, json={"message": "Workflow was started"})
        )
        with caplog.at_level("INFO", logger="app.services.events"):
            await publicar_evento("/turismo-dlq", DLQ_EVENT_EXAMPLE)

    assert rota.call_count == 1
    chamada = rota.calls.last
    assert chamada.request.headers["X-Webhook-Secret"] == "chave-n8n-teste"
    assert json.loads(chamada.request.content) == DLQ_EVENT_EXAMPLE
    assert obter_total_eventos_dlq() == 1
    assert "Iniciando envio de evento ao n8n" in caplog.text
    assert "evento enviado ao n8n" in caplog.text
    assert "chave-n8n-teste" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "efeito_n8n",
    [
        httpx.Response(500, json={"error": "erro interno n8n"}),
        httpx.ReadTimeout("timeout simulado no n8n"),
        httpx.ConnectError("conexão recusada"),
    ],
)
async def test_publicar_evento_nunca_propaga_excecao_quando_n8n_falha(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    efeito_n8n: httpx.Response | Exception,
) -> None:
    monkeypatch.setenv("N8N_WEBHOOK_BASE_URL", "https://n8n.exemplo.test/webhook")
    monkeypatch.setenv("N8N_WEBHOOK_SECRET", "segredo-nao-vazar")
    get_settings.cache_clear()

    with respx.mock(assert_all_called=True) as router:
        if isinstance(efeito_n8n, httpx.Response):
            router.post("https://n8n.exemplo.test/webhook/turismo-dlq").mock(
                return_value=efeito_n8n
            )
        else:
            router.post("https://n8n.exemplo.test/webhook/turismo-dlq").mock(
                side_effect=efeito_n8n
            )

        with caplog.at_level("ERROR", logger="app.services.events"):
            await publicar_evento("turismo-dlq", DLQ_EVENT_EXAMPLE)

    assert obter_total_eventos_dlq() == 0
    assert "falha ao publicar evento no n8n" in caplog.text
    assert "segredo-nao-vazar" not in caplog.text


def test_construir_evento_dlq_valida_contra_schema_e_redige_pii(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "staging")
    get_settings.cache_clear()

    try:
        raise RuntimeError(
            "Falha ao processar maria.silva@exemplo.com.br com Bearer tok_secreto_123 "
            + ("x" * 700)
        )
    except RuntimeError as exc:
        payload = construir_evento_dlq(
            exc=exc,
            trace_id="a1b2c3d4e5f64a7b8c9d0e1f2a3b4c5d",
            method="post",
            route="/api/v1/roteiros/planejar",
            status_code=500,
            language="en",
            is_test=False,
        )

    schema = _carregar_schema_dlq()
    jsonschema.validate(
        instance=payload,
        schema=schema,
        format_checker=jsonschema.FormatChecker(),
    )
    serializado = json.dumps(payload)
    assert "maria.silva@exemplo.com.br" not in serializado
    assert "tok_secreto_123" not in serializado
    assert payload["environment"] == "staging"
    assert payload["request"]["method"] == "POST"
    assert len(payload["error"]["message"]) <= 500
    assert len(payload["error"]["stack_trace"]) <= 3000


@pytest.mark.parametrize(
    ("cabecalho", "esperado"),
    [
        (None, "pt-BR"),
        ("", "pt-BR"),
        ("en", "en"),
        ("zh-cn,en;q=0.8", "zh-CN"),
        ("ar;q=0.9", "ar"),
        ("en;q=0", "pt-BR"),
        ("de-DE", "pt-BR"),
        ("x" * 200, "pt-BR"),
    ],
)
def test_resolver_idioma_seguro(cabecalho: str | None, esperado: str) -> None:
    assert resolver_idioma_seguro(cabecalho) == esperado


@pytest.mark.asyncio
async def test_executar_tarefa_com_dlq_captura_erro_e_publica_evento_valido(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("N8N_WEBHOOK_BASE_URL", "https://n8n.exemplo.test/webhook")
    monkeypatch.setenv("N8N_WEBHOOK_SECRET", "segredo-dlq")
    get_settings.cache_clear()

    def persistencia_quebrada(dados_sensivel: dict[str, str]) -> None:
        assert "email" in dados_sensivel
        raise OSError("disco cheio ao gravar arquivo de viagens")

    with respx.mock(assert_all_called=True) as router:
        rota = router.post("https://n8n.exemplo.test/webhook/turismo-dlq").mock(
            return_value=httpx.Response(202)
        )
        with caplog.at_level("ERROR", logger="app.services.events"):
            await executar_tarefa_com_dlq(
                persistencia_quebrada,
                {"email": "turista@privado.com", "foto": "https://img.exemplo/a.png"},
                trace_id="trace1234567890abcdef1234567890ab",
                method="POST",
                route="/api/v1/roteiros/planejar",
                language="es",
            )

    assert rota.call_count == 1
    enviado = json.loads(rota.calls.last.request.content)
    jsonschema.validate(
        instance=enviado,
        schema=_carregar_schema_dlq(),
        format_checker=jsonschema.FormatChecker(),
    )
    assert enviado["request"]["route"] == "/api/v1/roteiros/planejar"
    assert enviado["request"]["language"] == "es"
    assert "turista@privado.com" not in json.dumps(enviado)
    assert "img.exemplo" not in json.dumps(enviado)
