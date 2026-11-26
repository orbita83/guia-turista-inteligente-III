"""Testes da consulta de postos com a polilinha Teresina–Piripiri."""

import json
import logging
import os
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import jsonschema
import pytest
import yaml  # type: ignore[import-untyped]
from fastapi.testclient import TestClient

from app.core.config import REPOSITORY_ROOT, get_settings
from app.main import app
from app.schemas.postos import MAX_PONTOS_ROTA
from app.services import postos_anp_service

ENDPOINT = "/api/v1/postos/ao-longo-da-rota"
# Polilinha simplificada do OSRM, de (-5.0892, -42.8025) a (-4.2715, -41.7762).
# Dados viários © OpenStreetMap contributors (https://www.openstreetmap.org/copyright).
ROTA_BR343 = [
    (-5.089232, -42.802483),
    (-5.080676, -42.790777),
    (-5.077798, -42.74335),
    (-5.063506, -42.723366),
    (-5.063324, -42.700329),
    (-5.056057, -42.680005),
    (-5.071485, -42.626737),
    (-5.043978, -42.553627),
    (-5.047368, -42.514394),
    (-5.040502, -42.500145),
    (-5.038451, -42.449768),
    (-5.021461, -42.42694),
    (-4.995902, -42.408435),
    (-4.995161, -42.400407),
    (-4.979043, -42.380092),
    (-4.959375, -42.36443),
    (-4.942484, -42.333463),
    (-4.916908, -42.257155),
    (-4.869652, -42.218828),
    (-4.838051, -42.18386),
    (-4.840641, -42.174987),
    (-4.833783, -42.164618),
    (-4.814538, -42.155726),
    (-4.783946, -42.116786),
    (-4.727885, -42.105113),
    (-4.708933, -42.087927),
    (-4.672807, -42.077805),
    (-4.615644, -41.994876),
    (-4.605514, -41.988539),
    (-4.459736, -41.942254),
    (-4.356892, -41.813804),
    (-4.307105, -41.770419),
    (-4.29606, -41.777315),
    (-4.271481, -41.776007),
]

DADOS = postos_anp_service.DATA_DIR
CONTRATO = REPOSITORY_ROOT / "specs/003-integracao-eda-n8n/contracts/postos-api.yaml"


@pytest.fixture
def catalogo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setattr(postos_anp_service, "DATA_DIR", tmp_path)
    shutil.copyfile(DADOS / "postos_fixture.json", tmp_path / "postos_fixture.json")
    postos_anp_service._carregar_catalogo.cache_clear()
    yield tmp_path
    postos_anp_service._carregar_catalogo.cache_clear()


@pytest.fixture
def cliente(catalogo: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    settings = get_settings()
    monkeypatch.setattr(settings, "trips_file", catalogo / "viagens.json")
    monkeypatch.setattr(settings, "legacy_trips_file", catalogo / "legado.json")
    monkeypatch.setattr(settings, "app_env", "local")
    with TestClient(app) as client:
        yield client


def _autenticar(cliente: TestClient) -> None:
    assert cliente.post("/api/v1/auth/visitor").status_code == 200


def _validar_contrato(codigo: int, resposta: dict[str, Any]) -> None:
    contrato = yaml.safe_load(CONTRATO.read_text(encoding="utf-8"))
    schema = contrato["paths"][ENDPOINT]["post"]["responses"][str(codigo)]["content"]["application/json"]["schema"]
    jsonschema.Draft202012Validator(
        {**schema, "components": contrato["components"]},
        format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER,
    ).validate(resposta)


def test_exige_sessao(cliente: TestClient) -> None:
    resposta = cliente.post(ENDPOINT, json={"geometria": ROTA_BR343})
    assert resposta.status_code == 401
    _validar_contrato(401, resposta.json())


def test_br343_filtra_por_segmento_e_preserva_rating_zero(
    cliente: TestClient, caplog: pytest.LogCaptureFixture, catalogo: Path
) -> None:
    _autenticar(cliente)
    with caplog.at_level(logging.WARNING, logger=postos_anp_service.__name__):
        resposta = cliente.post(ENDPOINT, json={"geometria": ROTA_BR343})
        # A segunda requisição deve usar os dados da primeira leitura.
        (catalogo / "postos_fixture.json").unlink()
        raio_maior = cliente.post(ENDPOINT, json={"geometria": ROTA_BR343, "raio_km": 3.1})

    assert resposta.status_code == raio_maior.status_code == 200
    dados = resposta.json()
    _validar_contrato(200, dados)
    assert dados["data_reference_date"] == "2026-01-01"
    postos = dados["postos"]
    assert [posto["legal_name"] for posto in postos] == ["FIXTURE - posto A", "FIXTURE - posto B"]
    assert [posto["rank"] for posto in postos] == [1, 2]
    assert [posto["rating"] for posto in postos] == [0, None]
    # O posto A fica perto de um segmento, mas longe de ambos os vértices.
    assert postos[0]["distance_from_route_km"] < 0.12
    primeiro = raio_maior.json()["postos"][0]
    assert primeiro["legal_name"] == "FIXTURE - posto C"
    assert primeiro["distance_from_route_km"] == pytest.approx(3.0, abs=0.02)
    assert sum("Usando postos fictícios" in r.message for r in caplog.records) == 1


def test_ranqueia_por_anos_e_distancia_depois_da_avaliacao(catalogo: Path) -> None:
    base = json.loads((catalogo / "postos_fixture.json").read_text(encoding="utf-8"))
    curto = [(0.0, -50.0), (0.0, -49.99), (0.0, -49.99)]
    modelos = [
        (1, 4, 5, 0.012),
        (2, 4, 5, 0.002),
        (3, 4, 8, 0.015),
        (4, 5, 1, 0.016),
        (5, None, 10, 0.001),
    ]
    postos = [
        dict(base[0], cnpj=f"00.000.000/0000-{indice:02d}", rating=rating,
             authorization_years=anos, latitude=latitude, longitude=-49.995)
        for indice, rating, anos, latitude in modelos
    ]
    (catalogo / "postos_pi.json").write_text(json.dumps(postos), encoding="utf-8")
    resposta = postos_anp_service.consultar_postos(curto, 2, app_env="production")
    assert [posto.cnpj[-2:] for posto in resposta.postos] == ["04", "03", "02", "01", "05"]


@pytest.mark.parametrize(
    "payload",
    [
        {"geometria": []},
        {"geometria": [(-4.271481, -41.776007)]},
        {"geometria": [(48.856613, 2.352222), (51.507222, -0.1275)]},
        {"geometria": ["geometria-sensivel-123", (-4.271481, -41.776007)]},
        {"geometria": [[True, -41.776007], ROTA_BR343[-1]]},
        {"geometria": [ROTA_BR343[0]] * (MAX_PONTOS_ROTA + 1)},
        {"geometria": ROTA_BR343, "raio_km": 5.01},
        {"geometria": ROTA_BR343, "raio_km": 0},
    ],
)
def test_rejeita_entrada_sem_expor_valores(cliente: TestClient, payload: dict[str, Any]) -> None:
    _autenticar(cliente)
    resposta = cliente.post(ENDPOINT, json=payload)
    assert resposta.status_code == 422
    assert resposta.json() == {"detail": "Geometria ou raio de busca inválido."}
    _validar_contrato(422, resposta.json())


def test_catalogo_fora_do_ambiente_local_nao_usa_fixture(cliente: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _autenticar(cliente)
    for ambiente in ("staging", "production"):
        monkeypatch.setattr(get_settings(), "app_env", ambiente)
        resposta = cliente.post(ENDPOINT, json={"geometria": ROTA_BR343})
        assert resposta.status_code == 503
        _validar_contrato(503, resposta.json())


def test_catalogo_real_invalido_nao_vira_fixture(cliente: TestClient, catalogo: Path) -> None:
    _autenticar(cliente)
    (catalogo / "postos_pi.json").write_text("[]", encoding="utf-8")
    resposta = cliente.post(ENDPOINT, json={"geometria": ROTA_BR343})
    assert resposta.status_code == 503


def test_sem_postos_no_raio_retorna_lista_vazia(cliente: TestClient) -> None:
    _autenticar(cliente)
    resposta = cliente.post(ENDPOINT, json={"geometria": [(0, -50), (0, -49)]})
    assert resposta.status_code == 200
    assert resposta.json() == {"postos": [], "data_reference_date": "2026-01-01"}


def test_br343_com_catalogo_real(
    cliente: TestClient, catalogo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    arquivo = Path(os.getenv("POSTOS_ANP_TEST_CATALOGO", str(DADOS / "postos_pi.json")))
    if not arquivo.is_file() and not os.getenv("POSTOS_ANP_TEST_CATALOGO"):
        pytest.skip("Base real da issue #8 ainda não disponível neste checkout.")
    shutil.copyfile(arquivo, catalogo / "postos_pi.json")
    monkeypatch.setattr(get_settings(), "app_env", "production")
    _autenticar(cliente)
    resposta = cliente.post(ENDPOINT, json={"geometria": ROTA_BR343})
    assert resposta.status_code == 200
    dados = resposta.json()
    _validar_contrato(200, dados)
    postos = dados["postos"]
    assert any(posto["cnpj"] == "04.661.353/0001-93" for posto in postos)
    assert all(posto["distance_from_route_km"] <= 2 for posto in postos)
    assert [posto["rank"] for posto in postos] == list(range(1, len(postos) + 1))
    chaves = [
        (p["rating"] is None, -(p["rating"] or 0), -p["authorization_years"], p["distance_from_route_km"])
        for p in postos
    ]
    assert chaves == sorted(chaves)
