# Contratos — 003 Integração EDA com n8n

Status: **rascunho para aprovação na primeira hora**. Depois de aprovado, nenhum
contrato muda sem avisar no grupo e atualizar este arquivo.

## Arquivos

| Arquivo | O que define | Quem produz | Quem consome |
| --- | --- | --- | --- |
| `env.md` | Variáveis de ambiente do backend e credenciais do n8n | Todos | Todos |
| `support-api.yaml` | Endpoints de suporte (`/api/v1/suporte/*`) com `X-Support-Key` | Pessoa 1 | Pessoa 2 |
| `dlq-event.schema.json` | Evento de falha enviado ao webhook `turismo-dlq` | Pessoa 1 | Pessoa 2 |
| `dispatch-event.schema.json` | Pedido de entrega do roteiro ao webhook `turismo-despachar-roteiro` | Pessoas 4 e 5 | Pessoa 5 |
| `weather-webhook.schema.json` | Pedido e resposta do webhook `turismo-clima` | Pessoa 5 | Pessoas 4 e 5 |
| `i18n.md` | Idiomas aceitos e propagação do `Accept-Language` | Pessoa 4 | Pessoas 3, 4 e 5 |
| `postos-anp.md` | Campos do pop-up de posto no mapa | Pessoa 3 | Pessoa 3 |

## Regras gerais

- Todo evento enviado ao n8n leva `event_id` (UUID v4), `occurred_at` (ISO 8601 UTC)
  e `trace_id` (o mesmo `X-Request-ID` já gerado pelo `main.py`).
- Todo webhook do n8n exige o cabeçalho `X-Webhook-Secret` (Header Auth no nó Webhook).
- O backend envia eventos ao n8n sempre em `BackgroundTasks`; uma falha no envio
  é registrada em log e **nunca** quebra a resposta ao usuário.
- Campos são nomeados em inglês; textos exibidos ao usuário ficam em PT-BR ou no idioma pedido.

## Decisões a tomar na reunião

- [ ] Origem da "avaliação" do posto (Google Places, nota calculada ou dados de teste)
- [ ] Canal de e-mail: Gmail ou Resend
- [ ] API de WhatsApp: Meta Cloud API, Twilio, Evolution API ou só e-mail
- [ ] URL pública do n8n (n8n Cloud ou túnel do n8n local)
- [ ] Quem guarda os segredos reais (nunca no repositório)
