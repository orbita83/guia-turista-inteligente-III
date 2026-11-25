# Variáveis de ambiente

## Backend (`.env` na raiz; adicionar ao `.env.example` sem valores reais)

| Variável | Exemplo | Uso |
| --- | --- | --- |
| `N8N_WEBHOOK_BASE_URL` | `https://equipe.app.n8n.cloud/webhook` | Base dos webhooks; o backend monta `<base>/turismo-dlq` etc. |
| `N8N_WEBHOOK_SECRET` | `gere-um-segredo-longo` | Enviado no cabeçalho `X-Webhook-Secret` em toda chamada ao n8n |
| `N8N_TIMEOUT_SECONDS` | `5` | Timeout do `httpx` ao chamar o n8n |
| `SUPPORT_API_KEY` | `gere-outra-chave-longa` | Valor esperado no cabeçalho `X-Support-Key` dos endpoints de suporte (diferente de `N8N_WEBHOOK_SECRET`) |
| `APP_ENV` | `local` | `local`, `staging` ou `production`; vai no campo `environment` do evento DLQ |

Sem `N8N_WEBHOOK_BASE_URL`, o backend só registra o evento em log (modo local).
Sem `SUPPORT_API_KEY`, os endpoints de suporte respondem `503`.

## n8n (credenciais e variáveis do próprio n8n, nunca no repositório)

> **Compatibilidade de planos:** `Variables ($vars.*)` só existem nos planos Pro/Enterprise do n8n.
> No n8n Community (self-hosted gratuito) ou Cloud Starter, usar variáveis de ambiente (`$env.*`) ou um nó
> `Config (Set)` para `TELEGRAM_SUPPORT_CHAT_ID` e `BACKEND_BASE_URL`, e credencial **Header Auth**
> para `X-Support-Key` (nunca gravar segredos em texto puro nos JSONs exportados em `docs/n8n/`).
>
> **Decisão da equipe (n8n Cloud):** `TELEGRAM_SUPPORT_CHAT_ID` e `BACKEND_BASE_URL` ficam em um nó `Set` chamado `Config`, no início de cada workflow; não use `$env.*` nem `Variables`. O Chat ID real **não** vai nos JSONs exportados em `docs/n8n/` (troque por `<TELEGRAM_SUPPORT_CHAT_ID>` antes do commit). A URL real do workspace e os segredos são entregues por canal privado; este arquivo só documenta o formato (`https://<workspace>.app.n8n.cloud/webhook`).

| Nome | Uso |
| --- | --- |
| Credencial **Telegram API** (token do BotFather) | Workflows DLQ e ChatOps |
| `TELEGRAM_SUPPORT_CHAT_ID` | Único chat autorizado a receber alertas e enviar comandos |
| `BACKEND_BASE_URL` | URL do FastAPI que o ChatOps chama (ex.: túnel para `localhost:8001`) |
| `SUPPORT_API_KEY` | Mesmo valor do backend, enviado no `X-Support-Key` |
| Credencial **Header Auth** (`X-Webhook-Secret`) | Proteção dos webhooks |
| Credencial **SMTP** `cred-gmail` (Gmail com senha de app); plano B: nó Gmail com OAuth | Entrega de e-mail |
| Credencial da API de WhatsApp | Entrega por WhatsApp |
| Credencial **Gemini** | Orientações de clima |

## Webhooks (paths fixos)

| Path | Método | Resposta |
| --- | --- | --- |
| `/turismo-dlq` | POST | `202` imediato |
| `/turismo-despachar-roteiro` | POST | `202` imediato |
| `/turismo-clima` | POST | `200` com o corpo de `weather-webhook.schema.json` (nó Respond to Webhook) |
