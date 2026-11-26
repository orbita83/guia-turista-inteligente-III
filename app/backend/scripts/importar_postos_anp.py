"""Importa CSV da ANP, produtos da API e coordenadas conferidas manualmente.

A data disponível é a publicação da autorização, não necessariamente a data
em que ela foi concedida; é utilizada como aproximação documentada.
Coordenadas devem vir de JSON local: {"CNPJ somente dígitos": [lat, lon]}.
"""
import argparse
import csv
import json
import re
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path

PRODUTOS = {
    "GASOLINA C COMUM": "gasolina_comum",
    "GASOLINA C COMUM ADITIVADA": "gasolina_aditivada",
    "ETANOL HIDRATADO COMUM": "etanol",
    "ÓLEO DIESEL B S10 - COMUM": "diesel_s10",
    "ÓLEO DIESEL B S10 - ADITIVADO": "diesel_s10_aditivado",
    "ÓLEO DIESEL B S500 - COMUM": "diesel_s500",
    "GÁS NATURAL VEICULAR": "gnv",
}
SAIDA = Path(__file__).resolve().parents[1] / "static/data/postos_pi.json"


def texto(valor):
    return unicodedata.normalize("NFKD", valor).encode("ascii", "ignore").decode().upper().strip()


def cnpj_valido(cnpj):
    if not re.fullmatch(r"\d{14}", cnpj) or len(set(cnpj)) == 1:
        return False
    for tamanho, pesos in ((12, (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)),
                          (13, (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2))):
        resto = sum(int(n) * p for n, p in zip(cnpj[:tamanho], pesos)) % 11
        if int(cnpj[tamanho]) != (0 if resto < 2 else 11 - resto):
            return False
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path, help="CSV completo baixado da ANP")
    parser.add_argument("--api-json", type=Path, required=True, help="Resposta completa da API de combustíveis da ANP para Piripiri")
    parser.add_argument("--coordenadas", type=Path, required=True, help="JSON local com coordenadas conferidas por CNPJ")
    parser.add_argument("--data-referencia", required=True, help="Data de obtenção dos dados, AAAA-MM-DD")
    args = parser.parse_args()
    referencia = date.fromisoformat(args.data_referencia)
    with args.csv.open(encoding="utf-8-sig", newline="") as arquivo:
        postos = [r for r in csv.DictReader(arquivo, delimiter=";") if r["UF"].strip() == "PI" and texto(r["MUNICIPIO"]) == "PIRIPIRI"]
    resposta = json.loads(args.api_json.read_text(encoding="utf-8"))
    meta = resposta.get("searchPageFilter", {})
    registros = resposta.get("data", [])
    if not resposta.get("succeeded") or len(registros) != meta.get("totalRegistro") or meta.get("totalPagina", 1) != 1:
        raise ValueError("resposta incompleta da API; reúna e confira todas as páginas")
    api = {r["cnpj"]: r for r in registros}
    if len(api) != len(registros) or {r["CNPJ"] for r in postos} != set(api):
        raise ValueError("CNPJs do CSV e da API não coincidem; confira downloads e datas")
    coordenadas = json.loads(args.coordenadas.read_text(encoding="utf-8"))
    saida, excluidos = [], []
    for r in postos:
        cnpj = r["CNPJ"]
        if not cnpj_valido(cnpj):
            raise ValueError(f"CNPJ inválido: {cnpj}")
        dado = api[cnpj]
        if texto(dado["municipio"]) != "PIRIPIRI" or dado["uf"] != "PI":
            raise ValueError(f"município divergente para {cnpj}")
        if cnpj not in coordenadas:
            excluidos.append(cnpj)
            continue
        lat, lon = coordenadas[cnpj]
        if isinstance(lat, bool) or isinstance(lon, bool) or not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)) or not (-34 <= lat <= 6 and -74 <= lon <= -34):
            raise ValueError(f"coordenadas inválidas para {cnpj}")
        desconhecidos = {p["produto"] for p in dado["produtos"]} - PRODUTOS.keys()
        if desconhecidos:
            raise ValueError(f"produtos sem mapeamento para {cnpj}: {sorted(desconhecidos)}")
        publicada = datetime.strptime(r["DATAPUBLICACAO"], "%d/%m/%Y").date()
        if publicada > referencia or dado["dataPublicacao"] != r["DATAPUBLICACAO"]:
            raise ValueError(f"data inconsistente para {cnpj}")
        anos = referencia.year - publicada.year - ((referencia.month, referencia.day) < (publicada.month, publicada.day))
        endereco = ", ".join(x.strip() for x in (r["ENDERECO"], r["COMPLEMENTO"], r["BAIRRO"]) if x.strip())
        saida.append({"cnpj": f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}",
                      "legal_name": r["RAZAOSOCIAL"], "authorized_since": publicada.isoformat(),
                      "authorization_years": anos, "fuels": sorted({PRODUTOS[p["produto"]] for p in dado["produtos"]}),
                      "address": endereco, "city": "Piripiri", "latitude": lat, "longitude": lon,
                      "rating": None, "rating_source": None, "rating_collected_at": None,
                      "data_source": "ANP", "data_reference_date": referencia.isoformat()})
    if not saida:
        raise ValueError("nenhum posto com coordenada conferida; arquivo não gerado")
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(saida, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Encontrados: {len(postos)}; incluídos: {len(saida)}; sem coordenadas conferidas: {len(excluidos)}")
    if excluidos:
        print("CNPJs excluídos:", ", ".join(excluidos))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        sys.exit(1)
