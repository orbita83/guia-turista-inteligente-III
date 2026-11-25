# Matriz da spec 003 — quem edita o quê

> Este arquivo mora em `specs/003-integracao-eda-n8n/MATRIZ.md`, junto com os contratos (issue #1, PR #17).
> Toda issue da spec 003 aponta para ele. Se uma issue e este arquivo discordarem, vale este arquivo e
> quem notou avisa o grupo.

## 1. Pessoas

| Pessoa | Nome | Frente |
| --- | --- | --- |
| P1 | Mateus | Backend, DLQ, higienização, endpoints de suporte, túnel, smoke test |
| P2 | Mailson | n8n + Telegram (DLQ e ChatOps); dono das credenciais do n8n; PR dos contratos |
| P3 | Vitor | Postos ANP, ranqueamento, pop-up no mapa |
| P4 | Alisson | Chat com Gemini, multilíngue, template e montagem do README de evidências |
| P5 | Cássio | Despacho por e-mail/WhatsApp, clima, revisão de segredos nos JSONs do n8n |

## 2. Regras de branch e PR

1. A issue #1 mescla os contratos em `development` primeiro. **Depois disso**, toda branch sai de `development`.
2. Nome da branch: `feat/003-<tema>` (ex.: `feat/003-dlq-handler`). Um PR por issue, para `development`.
3. Revisão cruzada obrigatória antes do merge (o revisor lê o diff e roda os testes):

| Autor | Revisor |
| --- | --- |
| P1 | P2 |
| P2 | P1 |
| P3 | P5 |
| P4 | P3 |
| P5 | P4 |

4. Ordem de merge: **#1 → #18 → #13a (backend do idioma, quarta) → (demais backend e n8n em qualquer ordem) → frontend → #13b por último**.
5. Nunca commitar segredos. O `.env` real não vai para o repositório; só o `.env.example`.
6. Cada PR roda antes de abrir: `npm run check` e `npm test` (na raiz). Se falhar por algo que você não tocou, avise o grupo.

## 3. Quem pode editar os arquivos compartilhados

Depois que a issue #18 (PR 0) for mesclada, **só o dono listado edita o arquivo**. Quem precisar de uma
mudança pede no grupo; o dono faz um PR de 5 minutos.

| Arquivo | Único dono | Observação |
| --- | --- | --- |
| `app/backend/app/main.py` | P1 | O PR 0 já registra todos os routers |
| `app/backend/app/core/config.py` | P1 | O PR 0 já cria todas as variáveis da seção 5 |
| `.env.example` (raiz) | P1 | O PR 0 já tem todas as variáveis, sem valor real |
| `app/backend/requirements.txt`, `requirements-dev.txt`, `requirements.lock` | P1 | Regenerar o lock só no PR 0 |
| `app/backend/app/schemas/events.py` | P1 | Modelos Pydantic dos contratos (fonte única) |
| `app/backend/app/services/events.py` | P1 | Cliente que publica eventos no n8n |
| `app/backend/app/routers/suporte.py` | P1 | |
| `app/backend/app/routers/trips.py` | P1 | P5 **não** edita; o despacho fica em `routers/despacho.py` |
| `app/backend/app/routers/postos.py`, `services/postos_anp_service.py`, `schemas/postos.py` | P3 | |
| `app/backend/app/routers/chat.py`, `services/guide.py`, `schemas/chat.py` | P4 | |
| `app/backend/app/routers/despacho.py`, `services/dispatch.py`, `schemas/despacho.py` | P5 | |
| `app/frontend/src/App.tsx`, `components/index.ts`, `index.css` | P1 | O PR 0 já importa os pontos de encaixe |
| `app/frontend/src/services/api.ts` | P4 (só `requestHeaders`, Accept-Language) e P1 (só `obterTelemetriaOperacional`/`OperationalTelemetry`) | Funções diferentes. O PR 0 exporta `request` e `requestHeaders` |
| `app/frontend/src/types/domain.ts` | P1 | Tipos novos vão em `types/postos.ts`, `types/chat.ts`, `types/despacho.ts` |
| `components/MapaRota.tsx`, `services/postosApi.ts`, `types/postos.ts`, `styles/postos.css` | P3 | |
| `components/ChatIA.tsx`, `services/chatApi.ts`, `types/chat.ts`, `styles/chat.css`, seletor de idioma | P4 | |
| `components/EnvioRoteiro.tsx`, `components/TripNavigationTabs.tsx` (e seu teste), `services/despachoApi.ts`, `types/despacho.ts`, `styles/despacho.css` | P5 | |
| `components/ErroAmigavel.tsx`, `components/TelemetriaCard.tsx` | P1 | |
| `docs/n8n/turismo-dlq.json`, `docs/n8n/turismo-chatops.json` | P2 | |
| `docs/n8n/turismo-despachar-roteiro.json`, `docs/n8n/turismo-clima.json` | P5 | |
| `docs/evidencias/README.md` (template e índice) | P4 | Cada pessoa edita **só a sua seção** |
| `app/backend/static/data/postos_pi.json`, `postos_fixture.json`, `app/backend/scripts/*`, `contracts/postos-api.yaml` | P3 | |
| `app/backend/app/services/idioma.py`, `hooks/useIdioma.ts`, `components/SeletorIdioma.tsx`, `src/i18n/*` | P4 | O seletor é renderizado dentro de `ChatIA.tsx` |
| `scripts/tunel.ps1`, `scripts/smoke-003.ps1`, `docs/evidencias/smoke-checklist.md` | P1 | |
| `.github/*` (issue #21, opcional) | quem pegar a #21 | |
| `specs/003-integracao-eda-n8n/contracts/*` | P2 (após o merge da #1) | Mudança de contrato = PR com o rótulo `contrato` e aviso no grupo |

## 4. Nomes fixos criados pelo PR 0 (#18)

Estes nomes não mudam. As issues usam exatamente estes.

**Backend (`app/backend/app/`)**

| O quê | Caminho |
| --- | --- |
| Router de suporte | `routers/suporte.py`, prefixo `/api/v1/suporte` |
| Router de postos | `routers/postos.py`, prefixo `/api/v1/postos` |
| Router de chat | `routers/chat.py`, prefixo `/api/v1/chat` |
| Router de despacho | `routers/despacho.py`, prefixo `/api/v1/despacho` (**não** fica em `/api/v1/roteiros`, para não colidir com `/{trip_id}`) |
| Modelos dos contratos | `schemas/events.py` |
| Publicador de eventos | `services/events.py`, função `publicar_evento(background_tasks, webhook_path, payload)` |
| Serviço de postos ANP | `services/postos_anp_service.py` (o `postos_service.py` existente **não** muda) |
| Serviço de despacho | `services/dispatch.py` |

**Endpoints**

| Endpoint | Dono | Resposta |
| --- | --- | --- |
| `GET /api/v1/suporte/status`, `/uptime`, `/telemetria` e `POST /api/v1/suporte/testardlq` | P1 | Conforme `support-api.yaml` |
| `POST /api/v1/postos/ao-longo-da-rota` | P3 | Definido por P3 em `postos-api.yaml` |
| `POST /api/v1/chat/mensagens` | P4 | Definido na issue #11 |
| `POST /api/v1/despacho/roteiro` | P5 | `202 {"trace_id": "...", "scheduled": true}` |

**Frontend (`app/frontend/src/`)**: `services/postosApi.ts`, `services/chatApi.ts`, `services/despachoApi.ts`,
`types/postos.ts`, `types/chat.ts`, `types/despacho.ts`, `styles/postos.css`, `styles/chat.css`,
`styles/despacho.css`, `components/ChatIA.tsx`, `components/EnvioRoteiro.tsx`, `components/ErroAmigavel.tsx`.

## 5. Variáveis de ambiente (nomes fixos)

| Variável | Onde | Quem fornece |
| --- | --- | --- |
| `N8N_WEBHOOK_BASE_URL` | Backend | P2 (URL de **produção**: termina em `/webhook`, nunca `/webhook-test`) |
| `N8N_WEBHOOK_SECRET` | Backend e credencial Header Auth do n8n | P2 gera e passa no grupo privado |
| `N8N_TIMEOUT_SECONDS` | Backend | padrão `3` |
| `SUPPORT_API_KEY` | Backend e n8n | P1 gera; **diferente** de `N8N_WEBHOOK_SECRET` |
| `APP_ENV` | Backend | `local`, `staging` ou `production`; entra no campo `environment` do evento DLQ |
| `GEMINI_API_KEY` | Backend (já existe) e credencial do n8n | quem tiver a chave |
| `TELEGRAM_SUPPORT_CHAT_ID`, `BACKEND_BASE_URL` | n8n | P2 |
| `GOOGLE_PLACES_API_KEY` | **só** no terminal de P3, ao rodar o script offline; nunca em `.env` do repositório nem no backend | P3 |

Credenciais no n8n (nomes fixos, criadas **somente** por P2): `cred-telegram`, `cred-webhook-header`,
`cred-support-key`, `cred-gmail`, `cred-twilio`, `cred-gemini`.

## 6. De onde vem o `itinerary` do despacho (decisão única)

O endpoint `POST /api/v1/despacho/roteiro` aceita **`trip_id` ou `itinerary`** (um dos dois, nunca os dois):

- `trip_id`: o backend busca a viagem **do próprio usuário da sessão** (outro `trip_id` → `404`) e converte com
  `services/dispatch.py::viagem_para_itinerary` (**P5 escreve**).
- `itinerary`: usado pelo chat. O corpo é validado pelo modelo `Itinerary` de `schemas/events.py`
  (**P4 gera exatamente esse formato** na issue #11).

O frontend de P4 (botão "enviar" no chat) e o de P5 (botão nas abas da viagem) chamam o mesmo
`services/despachoApi.ts` (**P5 escreve**).

## 7. Evidências (nomes fixos em `docs/evidencias/`)

| Nº | Arquivo | Dono |
| --- | --- | --- |
| 1 | `01-workflows-ativos-n8n.png` | P2 (DLQ e ChatOps) e P5 (despacho e clima) enviam um print cada, no mesmo arquivo ou como `01a`/`01b` |
| 2 | `02-alerta-dlq-telegram.png` | P2 |
| 3 | `03-chatops-telegram.png` | P2 |
| 4 | `04-popup-posto-anp.png` | P3 |
| 5 | `05-chat-multilingue.png` (inglês + um idioma de outro alfabeto) | P4 |
| 6 | `06-roteiro-recebido.png` | P5 |
| 7 | `07-logs-backgroundtasks.log` | P1 |
| extra | `08-clima-resposta.png` | P5 (se o clima entrar) |

Prints nunca mostram tokens, chaves, e-mail pessoal completo ou número de telefone completo.

## 8. Dia a dia (hoje é 24/11, terça à noite)

| Quando | Entrega |
| --- | --- |
| Qua 25, até 12h | #1 e #18 mesclados. Bot do Telegram pronto (#5). Opt-in Twilio e test users do Gmail |
| Qua 25, tarde | Cada pessoa trabalha com mocks nas suas issues. P1 entrega #4a (suporte com respostas fixas). P4 entrega #13a (`resolver_idioma`) e o endpoint do chat com respostas fixas |
| Qui 26, manhã | #2, #3, #4b e túnel no ar. Workflows exportados |
| Qui 26, tarde | #20: smoke test integrado e as evidências. Reautenticar Gmail. **Congelar o código no fim do dia** |
| Sex 27 | Margem, README de evidências (#22) e entrega |

## 9. Se faltar tempo, corte nesta ordem

1. #21 (CI) 2. WhatsApp na #14 3. Workflow de clima (#16) 4. Idiomas além de `pt-BR`, `en` e `ar` na interface 5. Métricas extras.

## 10. Ordem das tarefas (ID `T####`)

O ID diz **quando a tarefa pode começar**, não que ela espera a anterior: tarefas da mesma onda rodam em paralelo.
O que bloqueia cada uma está em "Depende de" dentro da issue. Use o ID nas conversas ("T0007 pronta para revisão").

| ID | Issue | Quem | Quando |
| --- | --- | --- | --- |
| T0001 | #1 contratos | Mailson | Qua manhã |
| T0002 | #18 PR 0 (pontos de encaixe) | Mateus | Qua manhã |
| T0003 | #5 bot e credenciais | Mailson | Qua manhã |
| T0004 | #22 template do README | Alisson | Qua manhã |
| T0005 | #13 idioma (backend primeiro, frontend por último) | Alisson | Qua |
| T0006 | #2 handler da DLQ | Mateus | Qua |
| T0007 | #4 endpoints de suporte | Mateus | Qua |
| T0008 | #6 workflow DLQ | Mailson | Qua |
| T0009 | #7 workflow ChatOps | Mailson | Qua |
| T0010 | #8 base ANP | Vitor | Qua |
| T0011 | #9 API de postos | Vitor | Qua |
| T0012 | #11 chat (backend) | Alisson | Qua |
| T0013 | #14 workflow de despacho | Cássio | Qua |
| T0014 | #15 endpoint de despacho | Cássio | Qua |
| T0015 | #10 pop-up de posto | Vitor | Qua–Qui |
| T0016 | #12 chat (frontend) | Alisson | Qua–Qui |
| T0017 | #3 higienização | Mateus | Qui |
| T0018 | #19 túnel seguro | Mateus | Qui |
| T0019 | #20 smoke test | Mateus | Qui tarde |
| T0020 | #16 clima (bônus) | Cássio | só se sobrar tempo |
| T0021 | #21 CI (opcional) | quem sobrar | só se sobrar tempo |

## 11. Regras de conclusão (valem para todas as issues e para agentes de IA)

Todas as issues têm checkboxes em "Como fazer" e em "Critérios de aceite". Regras:

1. **Só marque o checkbox depois que a ação estiver concluída e verificável**: PR mesclado, comando verde, workflow ativo, print salvo. Marcar antes é proibido.
2. **A issue só fecha com todos os checkboxes marcados.** Item cortado por falta de tempo **não é marcado**: risque com `~~...~~` e escreva "CORTADO por <nome>: <motivo>".
3. **Deixe a prova** em um comentário (link do PR, saída do comando ou print). Sem prova, o revisor desmarca.
4. **Agentes de IA:** não marque por dedução. Execute o passo, confira o resultado e só então marque. Não edite arquivos fora de "Pode editar" (seção 3). Se um passo exigir arquivo de outro dono, pare e peça ao dono. Não invente credenciais, URLs, CNPJs ou dados de teste apresentados como reais.
5. Nas issues com duas entregas (T0007 = 4a/4b, T0005 = 13a/13b, T0004 = template/montagem), os passos de cada entrega só são marcados quando o PR **daquela** entrega for mesclado.
