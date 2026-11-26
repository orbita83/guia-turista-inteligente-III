"""Testes unitários e de contrato para resolução de idioma com Accept-Language (T0005 / #13a)."""

from __future__ import annotations

import pytest
from starlette.requests import Request

from app.routers.chat import obter_idioma_requisicao, preparar_instrucao_idioma_chat
from app.schemas.events import (
    DISPATCH_EVENT_EXAMPLE,
    DLQ_EVENT_EXAMPLE,
    WEATHER_REQUEST_EXAMPLE,
    DispatchEvent,
    DlqEvent,
    WeatherRequest,
)
from app.services.guide import montar_instrucao_idioma_chat
from app.services.idioma import (
    IDIOMA_PADRAO,
    IDIOMAS_ACEITOS,
    MAX_ACCEPT_LANGUAGE_BYTES,
    instrucao_idioma_prompt,
    resolver_idioma,
)


@pytest.mark.parametrize("codigo", IDIOMAS_ACEITOS)
def test_resolver_idioma_aceita_os_oito_codigos_do_contrato(codigo: str) -> None:
    assert resolver_idioma(codigo) == codigo
    assert resolver_idioma(f"  {codigo}  ") == codigo
    assert resolver_idioma(codigo.lower()) == codigo
    assert resolver_idioma(codigo.upper()) == codigo


def test_resolver_idioma_le_apenas_o_primeiro_valor_e_ignora_q_valido() -> None:
    assert resolver_idioma("en;q=0.9, pt-BR;q=0.8") == "en"
    assert resolver_idioma("ar, en;q=0.8") == "ar"
    assert resolver_idioma("zh-CN;q=1.0, fr;q=0.5") == "zh-CN"
    # Se o primeiro código não está na lista, não faz fallback para o segundo: cai em pt-BR.
    assert resolver_idioma("de, en;q=0.9") == IDIOMA_PADRAO
    assert resolver_idioma("it;q=0.9, es;q=0.8") == IDIOMA_PADRAO


@pytest.mark.parametrize(
    "entrada_invalida",
    [
        None,
        "",
        "   ",
        "*",
        "*;q=0.8",
        ",en",
        ";q=0.9",
        "de",
        "it-IT",
        "en-US",
        "pt",
        "pt-PT",
        "zh-TW",
        "en;q=0",
        "en;q=0.0",
        "en;q=0.000",
        "en;q=-0.5",
        "en;q=1.1",
        "en;q=abc",
        "en; invalid",
        "en;q=",
    ],
)
def test_resolver_idioma_retorna_pt_br_para_desconhecido_vazio_ou_q_zero(
    entrada_invalida: str | None,
) -> None:
    assert resolver_idioma(entrada_invalida) == IDIOMA_PADRAO


def test_resolver_idioma_respeita_limite_de_128_bytes() -> None:
    exato_128 = "en," + ("a" * (MAX_ACCEPT_LANGUAGE_BYTES - 3))
    assert len(exato_128.encode("utf-8")) == MAX_ACCEPT_LANGUAGE_BYTES
    assert resolver_idioma(exato_128) == "en"

    acima_128 = exato_128 + "a"
    assert len(acima_128.encode("utf-8")) == MAX_ACCEPT_LANGUAGE_BYTES + 1
    assert resolver_idioma(acima_128) == IDIOMA_PADRAO

    multibyte_acima_128 = "en," + ("á" * 63)  # 3 + 126 = 129 bytes em UTF-8
    assert len(multibyte_acima_128.encode("utf-8")) == 129
    assert resolver_idioma(multibyte_acima_128) == IDIOMA_PADRAO


@pytest.mark.parametrize("idioma", ["pt-BR", "en", "ar", "hi"])
def test_prompt_preserva_nomes_proprios_sem_traducao_em_multiplos_idiomas(
    idioma: str,
) -> None:
    instrucao = instrucao_idioma_prompt(idioma)
    assert f"código {idioma}" in instrucao
    assert "Parque Nacional de Sete Cidades" in instrucao
    assert "Cachoeira do Urubu" in instrucao
    assert "Maria Isabel" in instrucao
    assert montar_instrucao_idioma_chat(idioma) == instrucao


def test_router_chat_extrai_accept_language_e_repassa_ao_prompt() -> None:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/chat/mensagens",
        "headers": [(b"accept-language", b"en")],
    }
    request = Request(scope)
    assert obter_idioma_requisicao(request) == "en"

    instrucao = preparar_instrucao_idioma_chat(request)
    assert "código en" in instrucao
    assert "Parque Nacional de Sete Cidades" in instrucao
    assert "Cachoeira do Urubu" in instrucao


@pytest.mark.parametrize("codigo", IDIOMAS_ACEITOS)
def test_eventos_n8n_aceitam_language_resolvido_por_resolver_idioma(
    codigo: str,
) -> None:
    idioma = resolver_idioma(codigo)

    dlq = DlqEvent.model_validate(
        {
            **DLQ_EVENT_EXAMPLE,
            "request": {**DLQ_EVENT_EXAMPLE["request"], "language": idioma},
        }
    )
    assert dlq.request.language == codigo

    dispatch = DispatchEvent.model_validate(
        {**DISPATCH_EVENT_EXAMPLE, "language": idioma}
    )
    assert dispatch.language == codigo

    weather = WeatherRequest.model_validate(
        {**WEATHER_REQUEST_EXAMPLE, "language": idioma}
    )
    assert weather.language == codigo
