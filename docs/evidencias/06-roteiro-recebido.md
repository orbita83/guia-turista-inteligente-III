## Evidência 6 — Roteiro recebido (Pessoa 5 — Cássio)

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
