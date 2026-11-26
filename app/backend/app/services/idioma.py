"""Resolução padronizada do cabeçalho Accept-Language conforme contracts/i18n.md (T0005)."""

from __future__ import annotations

from typing import Final

IDIOMA_PADRAO: Final[str] = "pt-BR"

IDIOMAS_ACEITOS: Final[tuple[str, ...]] = (
    "pt-BR",
    "en",
    "es",
    "fr",
    "zh-CN",
    "hi",
    "ar",
    "ru",
)

NOMES_IDIOMAS: Final[dict[str, str]] = {
    "pt-BR": "Português (pt-BR)",
    "en": "Inglês (en)",
    "es": "Espanhol (es)",
    "fr": "Francês (fr)",
    "zh-CN": "Mandarim simplificado (zh-CN)",
    "hi": "Hindi (hi)",
    "ar": "Árabe (ar)",
    "ru": "Russo (ru)",
}

EXEMPLOS_NOMES_PROPRIOS_INTACTOS: Final[tuple[str, ...]] = (
    "Cachoeira do Urubu",
    "Parque Nacional de Sete Cidades",
    "Maria Isabel",
)

MAX_ACCEPT_LANGUAGE_BYTES: Final[int] = 128

_MAPA_IDIOMAS_CANONICOS: Final[dict[str, str]] = {
    codigo.lower(): codigo for codigo in IDIOMAS_ACEITOS
}


def _parametros_accept_language_validos(parametros: list[str]) -> bool:
    """Valida parâmetros opcionais (como q=) do primeiro item de Accept-Language."""
    for parametro in parametros:
        texto = parametro.strip()
        if not texto or "=" not in texto:
            return False
        chave, valor = (parte.strip() for parte in texto.split("=", 1))
        if not chave or not valor:
            return False
        if chave.lower() == "q":
            try:
                peso = float(valor)
            except ValueError:
                return False
            if not (0.0 < peso <= 1.0):
                return False
    return True


def resolver_idioma(accept_language: str | None) -> str:
    """Resolve o código de idioma a partir do cabeçalho Accept-Language.

    Regras do contrato (`specs/003-integracao-eda-n8n/contracts/i18n.md` e T0005):
    - Aceita exclusivamente os 8 códigos de `IDIOMAS_ACEITOS`.
    - Lê somente o primeiro valor antes de vírgula.
    - Ignora pesos `q=` válidos (`0 < q <= 1`), mas rejeita `q=0` ou parâmetros malformados.
    - Rejeita `*`, vazio, inválido ou cabeçalho maior que 128 bytes em UTF-8.
    - Qualquer valor fora da lista retorna `pt-BR`.
    """
    if not isinstance(accept_language, str):
        return IDIOMA_PADRAO

    if len(accept_language.encode("utf-8")) > MAX_ACCEPT_LANGUAGE_BYTES:
        return IDIOMA_PADRAO

    primeiro_item = accept_language.split(",", 1)[0].strip()
    if not primeiro_item:
        return IDIOMA_PADRAO

    partes = primeiro_item.split(";")
    codigo_bruto = partes[0].strip()
    if not codigo_bruto or codigo_bruto == "*":
        return IDIOMA_PADRAO

    if len(partes) > 1 and not _parametros_accept_language_validos(partes[1:]):
        return IDIOMA_PADRAO

    return _MAPA_IDIOMAS_CANONICOS.get(codigo_bruto.lower(), IDIOMA_PADRAO)


def instrucao_idioma_prompt(accept_language: str | None) -> str:
    """Monta a instrução de idioma e preservação de nomes próprios para o prompt do Gemini."""
    codigo = resolver_idioma(accept_language)
    nome = NOMES_IDIOMAS[codigo]
    exemplos = ", ".join(f'"{item}"' for item in EXEMPLOS_NOMES_PROPRIOS_INTACTOS)
    return (
        f"Responda obrigatoriamente no idioma {nome} (código {codigo}). "
        "Não traduza nomes próprios de patrimônios, atrativos, cidades e pratos locais "
        f"(ex.: {exemplos}); mantenha sempre o nome original em português e, se útil, "
        "explique o significado entre parênteses no idioma da resposta."
    )
