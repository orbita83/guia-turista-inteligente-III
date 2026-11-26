"""Testes de contrato, serviço e endpoint do diálogo com IA para montar o roteiro (T0012 / #11)."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Generator
from typing import Any

import httpx
import jsonschema
import pytest
from fastapi.testclient import TestClient

from app.core.circuit_breaker import CircuitState
from app.core.config import REPOSITORY_ROOT, Settings, get_settings
from app.main import app
from app.routers.chat import (
    _HISTORICO_MENSAGENS_POR_SESSAO,
    CHAT_RATE_LIMIT_WINDOW_SECONDS,
    MAX_CHAT_MESSAGES_PER_HOUR,
    limpar_rate_limit_chat,
)
from app.schemas.events import DISPATCH_EVENT_EXAMPLE, ITINERARY_EXAMPLE, Itinerary
from app.services import guide

CONTRACTS_DIR = REPOSITORY_ROOT / "specs" / "003-integracao-eda-n8n" / "contracts"


@pytest.fixture(autouse=True)
def _reset_chat_rate_limit() -> Generator[None, None, None]:
    limpar_rate_limit_chat()
    yield
    limpar_rate_limit_chat()


def _criar_cliente_autenticado(
    monkeypatch: pytest.MonkeyPatch,
    *,
    gemini_api_key: str = "test-gemini-key",
    gemini_timeout_seconds: float = 5.0,
) -> TestClient:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        secret_key="a" * 48,
        gemini_api_key=gemini_api_key,
        gemini_timeout_seconds=gemini_timeout_seconds,
    )
    app.dependency_overrides[get_settings] = lambda: settings
    client = TestClient(app)
    resp = client.post("/api/v1/auth/visitor")
    assert resp.status_code == 200
    return client


def test_chat_exige_sessao_autenticada() -> None:
    app.dependency_overrides.clear()
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chat/mensagens",
            json={
                "messages": [{"role": "user", "content": "Olá, quero planejar uma viagem"}],
                "origin": "Teresina - PI",
                "destination": "Piripiri - PI",
            },
        )
    assert response.status_code == 401


def test_chat_rejeita_mais_de_12_mensagens_ou_textos_longos_com_422(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _criar_cliente_autenticado(monkeypatch, gemini_api_key="")
    try:
        treze_mensagens = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"Mensagem {i}"}
            for i in range(13)
        ]
        resp_13 = client.post(
            "/api/v1/chat/mensagens",
            json={
                "messages": treze_mensagens,
                "origin": "Teresina - PI",
                "destination": "Piripiri - PI",
            },
        )
        assert resp_13.status_code == 422

        resp_content_longo = client.post(
            "/api/v1/chat/mensagens",
            json={
                "messages": [{"role": "user", "content": "a" * 1001}],
                "origin": "Teresina - PI",
                "destination": "Piripiri - PI",
            },
        )
        assert resp_content_longo.status_code == 422

        resp_content_espacos_longo = client.post(
            "/api/v1/chat/mensagens",
            json={
                "messages": [{"role": "user", "content": (" " * 1000) + "oi"}],
                "origin": "Teresina - PI",
                "destination": "Piripiri - PI",
            },
        )
        assert resp_content_espacos_longo.status_code == 422

        resp_origin_longo = client.post(
            "/api/v1/chat/mensagens",
            json={
                "messages": [{"role": "user", "content": "Quero viajar"}],
                "origin": "O" * 101,
                "destination": "Piripiri - PI",
            },
        )
        assert resp_origin_longo.status_code == 422

        resp_destination_longo = client.post(
            "/api/v1/chat/mensagens",
            json={
                "messages": [{"role": "user", "content": "Quero viajar"}],
                "origin": "Teresina - PI",
                "destination": "D" * 101,
            },
        )
        assert resp_destination_longo.status_code == 422

        resp_apenas_html = client.post(
            "/api/v1/chat/mensagens",
            json={
                "messages": [{"role": "user", "content": "<script></script><b></b>"}],
                "origin": "Teresina - PI",
                "destination": "Piripiri - PI",
            },
        )
        assert resp_apenas_html.status_code == 422
    finally:
        app.dependency_overrides.clear()
        client.close()


def test_chat_conversa_3_a_5_trocas_gera_itinerary_valido_contra_contrato(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    respostas_gemini = [
        json.dumps(
            {
                "reply": "Qual ritmo você prefere para a viagem: tranquilo, moderado ou intenso?",
                "done": False,
                "itinerary": None,
            },
            ensure_ascii=False,
        ),
        json.dumps(
            {
                "reply": "Perfeito! Com quem você vai viajar: sozinho, casal, família com crianças ou amigos?",
                "done": False,
                "itinerary": None,
            },
            ensure_ascii=False,
        ),
        json.dumps(
            {
                "reply": "Ótimo! Tem alguma preferência ou restrição de gastronomia?",
                "done": False,
                "itinerary": None,
            },
            ensure_ascii=False,
        ),
        json.dumps(
            {
                "reply": "Aqui está o seu roteiro personalizado para Piripiri!",
                "done": True,
                "itinerary": ITINERARY_EXAMPLE,
            },
            ensure_ascii=False,
        ),
    ]
    chamadas: list[dict[str, Any]] = []

    def fake_request_chat_json(
        messages: list[dict[str, str]],
        origin: str,
        destination: str,
        api_key: str,
        timeout_seconds: float,
        accept_language: str | None = None,
    ) -> str:
        indice = len(chamadas)
        chamadas.append(
            {
                "messages": messages,
                "origin": origin,
                "destination": destination,
                "accept_language": accept_language,
            }
        )
        return respostas_gemini[indice]

    monkeypatch.setattr(guide, "_request_chat_json", fake_request_chat_json)

    client = _criar_cliente_autenticado(monkeypatch)
    try:
        historico: list[dict[str, str]] = []
        entradas_usuario = [
            "Quero montar um roteiro de Teresina para Piripiri.",
            "Prefiro um ritmo tranquilo.",
            "Vou viajar em casal.",
            "Gostamos de culinária regional como Maria Isabel, sem restrições.",
        ]
        ultimo_corpo: dict[str, Any] = {}
        for entrada in entradas_usuario:
            historico.append({"role": "user", "content": entrada})
            resp = client.post(
                "/api/v1/chat/mensagens",
                json={
                    "messages": historico,
                    "origin": "Teresina - PI",
                    "destination": "Piripiri - PI",
                },
            )
            assert resp.status_code == 200
            ultimo_corpo = resp.json()
            historico.append({"role": "assistant", "content": ultimo_corpo["reply"]})

        assert ultimo_corpo["done"] is True
        assert ultimo_corpo["itinerary"] is not None
        itinerary_model = Itinerary.model_validate(ultimo_corpo["itinerary"])
        assert itinerary_model.origin == "Teresina - PI"
        assert itinerary_model.destination == "Piripiri - PI"

        # Valida também contra o JSON Schema oficial dispatch-event.schema.json
        schema = json.loads(
            (CONTRACTS_DIR / "dispatch-event.schema.json").read_text(encoding="utf-8")
        )
        evento_completo = {
            **DISPATCH_EVENT_EXAMPLE,
            "itinerary": ultimo_corpo["itinerary"],
        }
        jsonschema.validate(
            instance=evento_completo,
            schema=schema,
            format_checker=jsonschema.FormatChecker(),
        )
    finally:
        app.dependency_overrides.clear()
        client.close()


def test_chat_sem_gemini_api_key_responde_200_com_contingencia_guiada(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def nao_deve_chamar_gemini(*args: Any, **kwargs: Any) -> str:
        raise AssertionError("Gemini não deve ser chamado sem GEMINI_API_KEY")

    monkeypatch.setattr(guide, "_request_chat_json", nao_deve_chamar_gemini)
    client = _criar_cliente_autenticado(monkeypatch, gemini_api_key="   ")
    try:
        # 1ª troca: pergunta de ritmo
        r1 = client.post(
            "/api/v1/chat/mensagens",
            json={
                "messages": [{"role": "user", "content": "Olá"}],
                "origin": "Teresina - PI",
                "destination": "Piripiri - PI",
            },
        )
        assert r1.status_code == 200
        b1 = r1.json()
        assert b1["done"] is False
        assert b1["itinerary"] is None
        assert "Não consegui falar com a IA agora" in b1["reply"]
        assert "ritmo" in b1["reply"].lower()

        # 2ª troca: pergunta de acompanhantes
        r2 = client.post(
            "/api/v1/chat/mensagens",
            json={
                "messages": [
                    {"role": "user", "content": "Olá"},
                    {"role": "assistant", "content": b1["reply"]},
                    {"role": "user", "content": "Ritmo moderado"},
                ],
                "origin": "Teresina - PI",
                "destination": "Piripiri - PI",
            },
        )
        assert r2.status_code == 200
        b2 = r2.json()
        assert b2["done"] is False
        assert "acompanhantes" in b2["reply"].lower()

        # 3ª troca: pergunta de gastronomia
        r3 = client.post(
            "/api/v1/chat/mensagens",
            json={
                "messages": [
                    {"role": "user", "content": "Olá"},
                    {"role": "assistant", "content": b1["reply"]},
                    {"role": "user", "content": "Ritmo moderado"},
                    {"role": "assistant", "content": b2["reply"]},
                    {"role": "user", "content": "Casal"},
                ],
                "origin": "Teresina - PI",
                "destination": "Piripiri - PI",
            },
        )
        assert r3.status_code == 200
        b3 = r3.json()
        assert b3["done"] is False
        assert "gastronomia" in b3["reply"].lower()

        # 4ª troca: entrega roteiro de contingência válido pelo contrato Itinerary
        r4 = client.post(
            "/api/v1/chat/mensagens",
            json={
                "messages": [
                    {"role": "user", "content": "Olá"},
                    {"role": "assistant", "content": b1["reply"]},
                    {"role": "user", "content": "Ritmo moderado"},
                    {"role": "assistant", "content": b2["reply"]},
                    {"role": "user", "content": "Casal"},
                    {"role": "assistant", "content": b3["reply"]},
                    {"role": "user", "content": "Comida regional sem restrições"},
                ],
                "origin": "Teresina - PI",
                "destination": "Piripiri - PI",
            },
        )
        assert r4.status_code == 200
        b4 = r4.json()
        assert b4["done"] is True
        itinerary_contingencia = Itinerary.model_validate(b4["itinerary"])
        assert itinerary_contingencia.distance_km is None
        assert itinerary_contingencia.duration_min is None

        # Fallback em inglês (Accept-Language: en) mantém nomes próprios originais
        r_en = client.post(
            "/api/v1/chat/mensagens",
            headers={"Accept-Language": "en"},
            json={
                "messages": [{"role": "user", "content": "Hello"}],
                "origin": "Teresina - PI",
                "destination": "Parque Nacional de Sete Cidades",
            },
        )
        assert r_en.status_code == 200
        assert "I could not reach the AI right now" in r_en.json()["reply"]
    finally:
        app.dependency_overrides.clear()
        client.close()


def test_chat_timeout_responde_200_com_fallback_e_contabiliza_no_circuit_breaker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _timeout_gemini(*args: Any, **kwargs: Any) -> str:
        raise TimeoutError("Gemini timeout")

    monkeypatch.setattr(guide, "_request_chat_json", _timeout_gemini)
    client = _criar_cliente_autenticado(monkeypatch, gemini_timeout_seconds=0.05)
    try:
        breaker_guide = app.state.circuit_breakers["guide"]
        breaker_guide.state = CircuitState.CLOSED
        breaker_guide.failure_count = 0

        resp = client.post(
            "/api/v1/chat/mensagens",
            json={
                "messages": [{"role": "user", "content": "Quero viajar"}],
                "origin": "Teresina - PI",
                "destination": "Piripiri - PI",
            },
        )
        assert resp.status_code == 200
        assert "Não consegui falar com a IA agora" in resp.json()["reply"]
        assert breaker_guide.failure_count == 1
    finally:
        if hasattr(app.state, "circuit_breakers") and "guide" in app.state.circuit_breakers:
            breaker = app.state.circuit_breakers["guide"]
            breaker.state = CircuitState.CLOSED
            breaker.failure_count = 0
            breaker.opened_at = None
        app.dependency_overrides.clear()
        client.close()


def test_chat_json_invalido_faz_uma_nova_tentativa_e_cai_em_fallback_se_persistir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tentativas = 0

    def primeiro_invalido_segundo_valido(*args: Any, **kwargs: Any) -> str:
        nonlocal tentativas
        tentativas += 1
        if tentativas == 1:
            return "não é json válido"
        return json.dumps(
            {
                "reply": "Recuperado na segunda tentativa! Qual o ritmo desejado?",
                "done": False,
                "itinerary": None,
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(guide, "_request_chat_json", primeiro_invalido_segundo_valido)
    client = _criar_cliente_autenticado(monkeypatch)
    try:
        resp_retry_ok = client.post(
            "/api/v1/chat/mensagens",
            json={
                "messages": [{"role": "user", "content": "Quero viajar"}],
                "origin": "Teresina - PI",
                "destination": "Piripiri - PI",
            },
        )
        assert resp_retry_ok.status_code == 200
        assert tentativas == 2
        assert "Recuperado na segunda tentativa" in resp_retry_ok.json()["reply"]

        # Agora ambos inválidos -> 2 tentativas e fallback local
        tentativas_falha = 0

        def sempre_invalido(*args: Any, **kwargs: Any) -> str:
            nonlocal tentativas_falha
            tentativas_falha += 1
            return '{"reply": "Faltando itinerary com done true", "done": true, "itinerary": null}'

        monkeypatch.setattr(guide, "_request_chat_json", sempre_invalido)
        resp_fallback = client.post(
            "/api/v1/chat/mensagens",
            json={
                "messages": [{"role": "user", "content": "Quero viajar"}],
                "origin": "Teresina - PI",
                "destination": "Piripiri - PI",
            },
        )
        assert resp_fallback.status_code == 200
        assert tentativas_falha == 2
        assert "Não consegui falar com a IA agora" in resp_fallback.json()["reply"]
        # JSON inválido não deve abrir o circuit breaker compartilhado 'guide'
        assert app.state.circuit_breakers["guide"].failure_count == 0
    finally:
        app.dependency_overrides.clear()
        client.close()


def test_chat_reutiliza_circuit_breaker_guide_e_higieniza_entrada(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capturado: dict[str, Any] = {}

    def fake_request_chat_json(
        messages: list[dict[str, str]],
        origin: str,
        destination: str,
        api_key: str,
        timeout_seconds: float,
        accept_language: str | None = None,
    ) -> str:
        capturado["messages"] = messages
        capturado["origin"] = origin
        capturado["destination"] = destination
        capturado["accept_language"] = accept_language
        return json.dumps(
            {
                "reply": (
                    "Visit Parque Nacional de Sete Cidades and Cachoeira do Urubu! "
                    "Which pace do you prefer?"
                ),
                "done": False,
                "itinerary": None,
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(guide, "_request_chat_json", fake_request_chat_json)
    client = _criar_cliente_autenticado(monkeypatch)
    try:
        resp = client.post(
            "/api/v1/chat/mensagens",
            headers={"Accept-Language": "en"},
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": "<b>Quero</b> visitar   Parque Nacional de Sete Cidades\x00",
                    }
                ],
                "origin": "<i>Teresina - PI</i>",
                "destination": "<b>Piripiri - PI</b>",
            },
        )
        assert resp.status_code == 200
        assert capturado["messages"][0]["content"] == (
            "Quero visitar Parque Nacional de Sete Cidades"
        )
        assert capturado["origin"] == "Teresina - PI"
        assert capturado["destination"] == "Piripiri - PI"
        assert capturado["accept_language"] == "en"
        assert "Parque Nacional de Sete Cidades" in resp.json()["reply"]

        prompt_en = guide.montar_prompt_sistema_chat("en")
        assert "Parque Nacional de Sete Cidades" in prompt_en
        assert "Cachoeira do Urubu" in prompt_en
        assert "Maria Isabel" in prompt_en

        # Simula abertura do circuit breaker 'guide' e verifica fallback sem chamar Gemini
        breaker_guide = app.state.circuit_breakers["guide"]
        breaker_guide.state = CircuitState.OPEN
        breaker_guide.opened_at = time.monotonic()

        def nao_deve_ser_chamado(*args: Any, **kwargs: Any) -> str:
            raise httpx.ConnectError("não deveria chamar com breaker aberto")

        monkeypatch.setattr(guide, "_request_chat_json", nao_deve_ser_chamado)
        resp_breaker = client.post(
            "/api/v1/chat/mensagens",
            json={
                "messages": [{"role": "user", "content": "Olá"}],
                "origin": "Teresina - PI",
                "destination": "Piripiri - PI",
            },
        )
        assert resp_breaker.status_code == 200
        assert "Não consegui falar com a IA agora" in resp_breaker.json()["reply"]
    finally:
        if hasattr(app.state, "circuit_breakers") and "guide" in app.state.circuit_breakers:
            breaker = app.state.circuit_breakers["guide"]
            breaker.state = CircuitState.CLOSED
            breaker.failure_count = 0
            breaker.opened_at = None
        app.dependency_overrides.clear()
        client.close()


def test_chat_aplica_limite_de_20_mensagens_por_sessao_por_hora_e_nao_loga_conteudo(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    segredo_mensagem = "SEGREDO_SUPER_CONFIDENCIAL_DO_USUARIO_987654"
    client = _criar_cliente_autenticado(monkeypatch, gemini_api_key="")
    try:
        with caplog.at_level(logging.DEBUG):
            for _ in range(MAX_CHAT_MESSAGES_PER_HOUR):
                resp = client.post(
                    "/api/v1/chat/mensagens",
                    json={
                        "messages": [{"role": "user", "content": segredo_mensagem}],
                        "origin": "Teresina - PI",
                        "destination": "Piripiri - PI",
                    },
                )
                assert resp.status_code == 200

            resp_429 = client.post(
                "/api/v1/chat/mensagens",
                json={
                    "messages": [{"role": "user", "content": segredo_mensagem}],
                    "origin": "Teresina - PI",
                    "destination": "Piripiri - PI",
                },
            )
            assert resp_429.status_code == 429
            assert "20 mensagens por hora" in resp_429.json()["detail"]

        assert segredo_mensagem not in caplog.text
    finally:
        app.dependency_overrides.clear()
        client.close()


def test_chat_erro_4xx_gemini_nao_abre_circuit_breaker_e_rate_limit_remove_sessoes_expiradas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from google.genai import errors

    def _erro_chave_invalida(*args: Any, **kwargs: Any) -> str:
        raise errors.APIError(401, {"error": {"message": "API key not valid"}})

    monkeypatch.setattr(guide, "_request_chat_json", _erro_chave_invalida)
    client = _criar_cliente_autenticado(monkeypatch)
    try:
        breaker_guide = app.state.circuit_breakers["guide"]
        breaker_guide.state = CircuitState.CLOSED
        breaker_guide.failure_count = 0

        # Simula uma sessão antiga expirada em memória para verificar limpeza automática
        _HISTORICO_MENSAGENS_POR_SESSAO["session:expirada-antiga"] = [
            time.monotonic() - (CHAT_RATE_LIMIT_WINDOW_SECONDS + 10.0)
        ]

        resp = client.post(
            "/api/v1/chat/mensagens",
            headers={"Accept-Language": "es"},
            json={
                "messages": [{"role": "user", "content": "Hola"}],
                "origin": "Teresina - PI",
                "destination": "Parque Nacional de Sete Cidades",
            },
        )
        assert resp.status_code == 200
        assert "No pude comunicarme con la IA ahora" in resp.json()["reply"]
        # Erro 401 de chave não deve abrir o circuit breaker compartilhado 'guide'
        assert breaker_guide.failure_count == 0
        assert breaker_guide.state == CircuitState.CLOSED
        # A chave expirada deve ter sido removida do dicionário em memória
        assert "session:expirada-antiga" not in _HISTORICO_MENSAGENS_POR_SESSAO
    finally:
        app.dependency_overrides.clear()
        client.close()

