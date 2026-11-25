## Evidência 6 — Roteiro recebido (Pessoa 5 — Cássio)

**O que mostra:** e-mail real recebido pelo Gmail a partir do workflow
`turismo-despachar-roteiro`, em inglês, com dois dias de atividades, link do mapa
e a sequência `<script>alert(1)</script>` exibida como texto.

**Arquivo:** [06-roteiro-recebido.png](06-roteiro-recebido.png).

**Data/hora:** 25/11/2026; e-mails em português e inglês recebidos às 16:11 e
16:13, respectivamente (horário de Brasília).

**Como reproduzir:** configure as credenciais `cred-gmail` (SMTP) e
`cred-webhook-header` nos nós correspondentes, e o remetente no nó `Config`.
Clique em executar o workflow e envie um POST para a URL de teste do webhook,
com `X-Webhook-Secret` e um evento válido de `dispatch-event.schema.json`.
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
Após essa execução inicial, Cássio confirmou no chat que todos os testes
restantes foram concluídos e solicitou o encerramento da issue. Essa
confirmação inclui os critérios restantes de publicação, deduplicação e
alerta pela DLQ; não representa uma nova execução observada pelo agente.
O JSON versionado é portável e sanitizado, com credenciais e remetente como
marcadores e `active: false` para importação; esse campo não descreve o
estado atual da instância da equipe. WhatsApp (P2) ficou fora da entrega
combinada de e-mail em `pt-BR` e `en`. Esta seção é a contribuição de P5; o índice e as demais
seções de evidências serão consolidados pelo responsável pela documentação.
