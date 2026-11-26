## Evidência 6 — Roteiro recebido (Pessoa 5 — Cássio)

**Evidência 1b — workflow ativo:** [01b-workflows-p5-n8n.png](01b-workflows-p5-n8n.png), captura fornecida por Cássio em 25/11/2026. Mostra o workflow completo `turismo-despachar-roteiro` e o indicador `Published`, sem segredos visíveis.

**O que mostra:** e-mail real recebido pelo Gmail a partir do workflow
`turismo-despachar-roteiro`, em inglês, com dois dias de atividades, link do mapa
e a sequência `<script>alert(1)</script>` exibida como texto.

**Arquivo:** [06-roteiro-recebido.png](06-roteiro-recebido.png).

**Data/hora:** 25/11/2026; e-mails em português e inglês recebidos às 16:11 e
16:13, respectivamente (horário de Brasília).

**Como reproduzir:** configure as credenciais `cred-gmail` (SMTP) e
`cred-webhook-header` nos nós correspondentes, e o remetente no nó `Config`.
Na instância publicada, envie um POST para
`<N8N_WEBHOOK_BASE_URL>/turismo-despachar-roteiro`, com a base terminando em
`/webhook` (URL de produção), `X-Webhook-Secret` e um evento válido de
`dispatch-event.schema.json`. O modo de teste é útil para depurar um envio,
mas não comprova a deduplicação persistente.
Use seu próprio e-mail, um UUID novo em `event_id`, dois dias de atividades
e `language` igual a `pt-BR` ou `en`. Confira o `202`, a execução até
`Registrar entrega` e o recebimento na caixa de entrada.

**Resultados verificados nesta validação:**

- Envio real em português e inglês: mensagens recebidas na caixa de entrada.
- Conteúdo em inglês: `Day 1`, `Day 2` e `View on map`, preservando os nomes
  próprios do roteiro.
- Texto HTML de teste exibido literalmente no e-mail, sem interpretar a tag.
- Pedido sem o cabeçalho de autenticação: `403 Forbidden`.
- Destinatário inválido: rejeitado pela validação e encaminhado ao ramo da DLQ.
- Chamada à DLQ: falhou com `404`, pois o webhook de produção
  `turismo-dlq` não estava registrado/ativo no momento do teste. Portanto,
  o alerta no Telegram não foi comprovado nessa execução inicial.

**Observações:** a captura é de uma entrega real, sem endereço de e-mail
completo ou segredo visível. Os dados do roteiro são fictícios para teste.
Na revisão do PR #25, Mailson informou que a DLQ foi ativada em produção
(PR #26). A confirmação anterior de conclusão pelo responsável não
substitui a prova do reteste integrado: publicação do despacho, descarte
de evento repetido e alerta no Telegram devem ser registrados com
evidências antes da conclusão técnica da entrega.
O JSON versionado é portável e sanitizado, com credenciais e remetente como
marcadores e `active: false` para importação; esse campo não descreve o
estado atual da instância da equipe. WhatsApp (P2) ficou fora da entrega
combinada de e-mail em `pt-BR` e `en`.

Este arquivo é a contribuição de P5 para a Evidência 6. O README/índice
compartilhado pertence à #22 (Alisson); esta entrega não cria nem substitui
seu template. A seção pode ser incorporada ou vinculada pelo responsável
quando a #22 for consolidada.


### Reteste do receptor da DLQ com o `.env` configurado

Em 25/11/2026, o evento gerado pelo nó `Montar DLQ`, marcado com
`is_test: true` e sem dados pessoais, foi enviado diretamente ao receptor
de produção `/webhook/turismo-dlq`, usando o segredo local sem exibi-lo.

- Resposta: `HTTP 202`, corpo `{"message":"Workflow was started"}`.
- `event_id`: `2fcaeee3-c961-4432-b5aa-06adb7de96ba`.
- `trace_id`: `b19e4bdf23ec4950b30353e23dd21b71`.
- Tipo de erro do evento: `InvalidRecipient`.

A tentativa anterior de entrar pelo dispatcher de produção
`/webhook/turismo-despachar-roteiro` retornou `404` com a mensagem de webhook
não registrado. Portanto, este reteste confirma que a URL e o segredo
locais são aceitos pelo receptor da DLQ; não comprova a ativação do
despacho, sua deduplicação ou a entrega do alerta no Telegram. A execução
integrada continua pendente. O navegador não pôde ser controlado nesta
rodada porque a ferramenta não conseguiu confirmar a URL atual com segurança.

**Confirmação do alerta:** após esse POST, Cássio conferiu o grupo técnico
do Telegram e confirmou no chat o recebimento do alerta `[TESTE]` de
`InvalidRecipient` com `trace_id` começando por `b19e4bdf`, correspondente
ao evento acima. A entrega no Telegram foi confirmada pelo responsável;
a ferramenta não capturou uma nova imagem do grupo. Isso conclui o reteste
direto do receptor da DLQ, mantendo pendentes a execução integrada pelo
workflow de despacho publicado e a deduplicação em produção.


### Reteste pelo dispatcher publicado

Após Cássio publicar o workflow, em 25/11/2026 foram enviados três
pedidos à URL de produção do despacho, usando o segredo local:

- envio valido: `HTTP 202`.
- mesmo evento reenviado: `HTTP 202`.
- falha pelo dispatcher publicado: `HTTP 202`.

O envio válido e a repetição usaram o mesmo `event_id`: `d0b75fdd-feb0-4583-bbb9-cdeb10272953`.
O teste de falha usou destinatário inválido, `event_id`
`f6a0c061-1b8a-4dc1-a2ad-b69f35bd5335` e `trace_id`
`818d4ae8bd9c4421ac9e24b802cf1a9f`.

Essas respostas comprovam o recebimento pelo dispatcher de produção,
mas não são suficientes, isoladamente, para comprovar ausência de
e-mail duplicado ou entrega do alerta no Telegram. Cássio confirmou no chat o recebimento de exatamente um e-mail
com assunto "Validação final de duplicidade T0013" após os dois pedidos
com o mesmo `event_id`, e o alerta `InvalidRecipient` no Telegram com
rastreio começando por `818d4ae8`. A confirmação das entregas foi feita
pelo responsável, correlacionada aos eventos desta execução; não foi
capturada nova imagem do grupo pela ferramenta.

O reteste integrado e a duplicidade em produção ficam registrados como
concluídos com essa atribuição. A captura 01b do workflow ativo foi anexada. Resta concluir a
revisão/merge do PR #25.
