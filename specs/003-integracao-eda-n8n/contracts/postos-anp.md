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
