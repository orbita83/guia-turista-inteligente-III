# Postos ANP no mapa

## Campos do pop-up

| Campo | Tipo | Fonte |
| --- | --- | --- |
| `cnpj` | string formatada `00.000.000/0000-00` | Dados abertos da ANP |
| `legal_name` (Razão Social) | string | Dados abertos da ANP |
| `rating` (avaliação) | number 0–5 ou `null` | **A decidir na reunião** (a ANP não fornece) |
| `authorized_since` | date | Dados abertos da ANP |
| `authorization_years` | integer | Calculado a partir de `authorized_since` |
| `fuels` | string[] (ex.: `["gasolina_comum", "etanol", "diesel_s10"]`) | Dados abertos da ANP |
| `latitude` / `longitude` | number | Geocodificação do endereço ou base de referência |
| `distance_from_route_km` | number | Calculado |

## Regras

- O pop-up abre **somente** por clique no marcador (sem hover).
- Ranqueamento: postos até 2 km da rota, ordenados por `rating` (desc), depois `authorization_years` (desc), depois `distance_from_route_km` (asc). Critérios a confirmar.
- Caso de validação: trecho da BR-343 em Piripiri (PI).
- A Pessoa 3 escreve o OpenAPI do endpoint de postos (`postos-api.yaml`) a partir deste arquivo até 1h30 de trabalho.

## Fonte

- Dados cadastrais do [CSV aberto da ANP](https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/dados-cadastrais-dos-revendedores-varejistas-de-combustiveis-automotivos), complementados pelos produtos da [API de revendedores da ANP](https://www.gov.br/anp/pt-br/centrais-de-conteudo/paineis-dinamicos-da-anp/paineis-dinamicos-do-abastecimento/painel-dinamico-de-relatorio-de-revenda). Consulta e download em 2026-11-25; ambos retornaram os mesmos 22 CNPJs de Piripiri.
- `authorized_since` usa a data de **publicação da autorização** como aproximação: essa é a descrição de `DATAPUBLICACAO` nos [metadados da ANP](https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/arquivos-dados-cadastrais-dos-revendedores-varejistas-de-combustiveis-automotivos/metadados-revendedores-varejistas-combustiveis-automoveis.pdf). Não representa necessariamente a data de concessão. `authorization_years` é calculado em anos completos até a data de referência da coleta.
- As coordenadas dos 11 registros incluídos vieram da API da ANP e foram confrontadas individualmente com a via e o município retornados pelo Nominatim/OpenStreetMap. A consulta confirma a correspondência da via, **não o número exato do imóvel**. A ANP classificou essas posições como não validadas; são aproximações e devem ser revistas antes de uso que exija precisão. Dados de mapa © colaboradores do OpenStreetMap.
- Dos 22 registros, sete não tinham coordenadas na API e quatro tinham localização divergente ou insuficiente para confirmar a via. Um dos pontos divergentes foi localizado em Teresina, não em Piripiri. Os 11 foram excluídos do JSON, sem substituir as posições por centros de ruas. A cobertura é parcial.
- Para reproduzir, obtenha o CSV completo e as respostas da API para `uf=PI&municipio=PIRIPIRI`; em `--api-json`, forneça uma resposta única ou uma lista JSON com todas as respostas de páginas. Forneça também um JSON local que mapeie cada CNPJ conferido (somente dígitos) para `[latitude, longitude]` e a data de obtenção, usando `--coordenadas` e `--data-referencia`. O importador rejeita páginas incompletas, CNPJs divergentes ou duplicados, CNPJ inválido, produtos não mapeados e data inconsistente. Os arquivos de entrada e de conferência não são versionados.

## Origem da avaliação

Nenhuma avaliação foi coletada nesta entrega: `rating`, `rating_source` e `rating_collected_at` são `null`. O uso do Google Places com armazenamento no repositório permanece pendente de revisão pela equipe conforme as [políticas do serviço](https://developers.google.com/maps/documentation/places/web-service/policies). A aplicação deve apresentar o valor nulo como ausência de avaliação.
