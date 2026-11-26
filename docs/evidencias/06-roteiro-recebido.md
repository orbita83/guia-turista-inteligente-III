# Evidências de P5 — despacho de roteiro por e-mail

## Estado atual

O workflow `turismo-despachar-roteiro` foi publicado por Cássio. Os testes
pela URL de produção receberam `202`; Cássio confirmou a entrega única do
e-mail após repetição do evento e o alerta de falha correspondente no
Telegram. A captura 01b comprova a publicação. Resta a revisão e o merge
do PR #25; a issue #14 permanece aberta até essa conclusão.

## Arquivos

| Evidência | Arquivo | O que comprova |
| --- | --- | --- |
| 1b | [01b-workflows-p5-n8n.png](01b-workflows-p5-n8n.png) | Captura fornecida por Cássio em 25/11/2026: fluxo completo e indicador `Published`, sem segredos visíveis. |
| 6 | [06-roteiro-recebido.png](06-roteiro-recebido.png) | E-mail real em inglês, com dois dias, mapa e texto HTML escapado; sem endereço de e-mail completo visível. |

Ambos os arquivos usam formato PNG real. A conversão da Evidência 6 de
JPEG para PNG preservou todos os pixels da captura original.

## Configuração e reprodução

1. Importe o [workflow](../n8n/turismo-despachar-roteiro.json) e selecione
   `cred-webhook-header` (Header Auth com `X-Webhook-Secret`) nos nós
   `Webhook` e `Enviar DLQ`, e `cred-gmail` (SMTP) em `Enviar email SMTP`.
2. Para Gmail SMTP: host `smtp.gmail.com`, porta `465`, SSL/TLS ligado e
   senha de aplicativo. Não use a senha comum da conta.
3. No nó `Config`, preencha `fromEmail` com a conta remetente autenticada
   e `environment` com `local`, `staging` ou `production`, conforme o ambiente.
4. Publique o despacho. Para o alerta integrado, `turismo-dlq` também deve
   estar ativo na mesma instância e aceitar a mesma credencial de webhook.
5. Envie um POST para `<N8N_WEBHOOK_BASE_URL>/turismo-despachar-roteiro`.
   A base deve terminar em `/webhook` (produção). Inclua `X-Webhook-Secret`
   e um evento do [contrato de despacho](../../specs/003-integracao-eda-n8n/contracts/dispatch-event.schema.json),
   sem `schema_version`, com seu e-mail, dois dias de atividades e
   `language` igual a `pt-BR` ou `en`.
6. Confira `202`, a execução até `Registrar entrega` e a caixa de entrada.
   Reenvie exatamente o mesmo `event_id`, após a primeira execução terminar:
   deve haver apenas um e-mail. Use um UUID novo para outro envio independente.
7. Para repetir o cenário de falha registrado, envie um novo evento com
   destinatário inválido e confira o alerta `InvalidRecipient` no Telegram,
   correlacionando o `trace_id`. Sem a chave correta, a chamada deve ser recusada.

O `.env` da raiz fornece URL e segredo ao backend ou ao disparo HTTP local.
O workflow no n8n Cloud usa as credenciais e o nó `Config`; ele não lê o
`.env` do repositório. A URL de teste permite depurar uma execução, mas não
comprova deduplicação persistente.

## Resultados registrados em 25/11/2026

| Cenário | Resultado e origem da confirmação |
| --- | --- |
| Português e inglês | Mensagens recebidas às 16:11 e 16:13 (Brasília), respectivamente, observadas na caixa de entrada. |
| Conteúdo em inglês | `Day 1`, `Day 2`, `View on map` e nomes próprios preservados, observados no e-mail. |
| Escape HTML | A sequência `<script>alert(1)</script>` aparece como texto no e-mail. |
| Pedido sem autenticação | `403 Forbidden`, observado na resposta HTTP. |
| Despacho de produção | Envio válido, repetição do mesmo evento e destinatário inválido retornaram `202`, observados nas respostas HTTP. |
| Deduplicação de produção | Cássio confirmou exatamente um e-mail com assunto exclusivo "Validação final de duplicidade T0013" após os dois pedidos com o mesmo evento. |
| DLQ pelo despacho publicado | Cássio confirmou o alerta `InvalidRecipient` no Telegram com rastreio correspondente ao evento de falha. Não foi capturada nova imagem do grupo pelo agente. |

O `202` comprova aceitação do pedido, não entrega. A entrega única e o
alerta em produção foram confirmados por Cássio, correlacionados aos
pedidos abaixo, e não são apresentados como inspeção direta do agente no Telegram.

- Evento válido e sua repetição: `d0b75fdd-feb0-4583-bbb9-cdeb10272953`.
- Evento de falha integrado: `f6a0c061-1b8a-4dc1-a2ad-b69f35bd5335`.
- Rastreio do alerta integrado: `818d4ae8bd9c4421ac9e24b802cf1a9f`.
- Reteste direto anterior do receptor da DLQ: `202`, evento
  `2fcaeee3-c961-4432-b5aa-06adb7de96ba`, rastreio
  `b19e4bdf23ec4950b30353e23dd21b71`, `is_test: true`; alerta também
  confirmado por Cássio.

Os `404` dos testes iniciais ocorreram antes de os respectivos webhooks
estarem ativos em produção. São histórico do diagnóstico, não pendência
atual: o reteste integrado acima ocorreu após a publicação do despacho.

## Escopo, limites e integração com a documentação da equipe

- Entrega P0: e-mail em `pt-BR` e `en`. WhatsApp (P2) e idiomas adicionais
  foram cortados conforme registro na issue; o ramo de WhatsApp informa
  que o canal não está habilitado, sem simular entrega.
- O cenário de falha efetivamente executado usa destinatário barrado pela
  validação. Não é prova de indisponibilidade ou rejeição pelo servidor SMTP;
  esses erros têm um ramo próprio no workflow.
- A deduplicação mantém os últimos 50 eventos entregues, usa static data
  somente após sucesso e exige workflow publicado. Não há garantia atômica
  para chamadas simultâneas nem para falha após o provedor aceitar o e-mail.
- O JSON versionado é portável e sanitizado: credenciais e remetente são
  marcadores, `pinData` é vazio e `active: false` evita ativação na importação.
  Isso não contradiz a instância publicada mostrada na Evidência 1b.
- Revisão adicional em 26/11/2026: resumo e descrição não têm mais o teto
  local de 500 caracteres, acompanhando o contrato e o modelo Pydantic;
  o texto completo continua escapado no HTML. Falhas de validação preservam
  `pt-BR`/`en` (fallback `pt-BR`) e resumo vazio não gera parágrafo.
- Testes locais de regressão:
  `node --test docs/n8n/turismo-despachar-roteiro.test.mjs` (23 testes),
  incluindo textos com mais de 5.000 caracteres e erro SMTP com DLQ segura
  e possibilidade de retentativa. São testes em VM dos nós Code e das
  conexões exportadas; não simulam uma rejeição real do servidor SMTP.
- As evidências de produção de 25/11/2026 correspondem à versão publicada
  naquele dia. A revisão de 26/11/2026 foi validada localmente; atualizar
  o JSON no repositório não publica automaticamente a alteração no n8n.
- Este arquivo é a contribuição de P5. O README/índice compartilhado pertence
  à #22 (Alisson), que pode incorporar ou vincular esta seção; este PR não
  cria nem substitui o template.
