import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const workflow = JSON.parse(readFileSync(new URL('./turismo-despachar-roteiro.json', import.meta.url)));
const fixture = () => ({
  event_type: 'turismo.roteiro.despachar',
  event_id: '12345678-1234-4234-8234-123456789012',
  occurred_at: '2026-11-25T12:00:00Z',
  trace_id: 'fixture-trace',
  channel: 'email',
  recipient: { name: 'Viajante', email: 'fixture@example.invalid' },
  language: 'pt-BR',
  itinerary: {
    trip_id: 'fixture', title: 'Passeio', origin: 'Teresina', destination: 'Piripiri',
    days: [{ day: 1, activities: [{ title: 'Parque Nacional de Sete Cidades' }] }],
  },
});

function run(name, input, { state = {}, references = {} } = {}) {
  const node = workflow.nodes.find((candidate) => candidate.name === name);
  assert.ok(node, `Nó ausente: ${name}`);
  return vm.runInNewContext(`(function () { ${node.parameters.jsCode}\n})()`, {
    $input: { first: () => ({ json: input }) },
    $getWorkflowStaticData: () => state,
    $: (nodeName) => ({ first: () => ({ json: references[nodeName] ?? {
      fromEmail: 'sender@example.invalid', environment: 'local',
    } }) }),
  });
}

for (const field of ['summary', 'distance_km', 'duration_min', 'map_url']) {
  test(`aceita itinerary.${field} nulo vindo do modelo Pydantic`, () => {
    const event = fixture();
    event.itinerary[field] = null;
    assert.equal(run('Validar e deduplicar', { body: event })[0].json.valid, true);
  });
}

for (const field of ['time', 'description']) {
  test(`aceita activity.${field} nulo vindo do modelo Pydantic`, () => {
    const event = fixture();
    event.itinerary.days[0].activities[0][field] = null;
    assert.equal(run('Validar e deduplicar', { body: event })[0].json.valid, true);
  });
}

test('aceita todos os opcionais nulos juntos, incluindo telefone não utilizado', () => {
  const event = fixture();
  Object.assign(event.itinerary, { summary: null, distance_km: null, duration_min: null, map_url: null });
  Object.assign(event.itinerary.days[0].activities[0], { time: null, description: null });
  event.recipient.phone = null;
  assert.equal(run('Validar e deduplicar', { body: event })[0].json.valid, true);
  const email = run('Montar email', { event })[0].json;
  assert.doesNotMatch(email.html, /null|undefined/);
  assert.doesNotMatch(email.html, /href=/);
});

test('continua rejeitando tipos inválidos em campos opcionais preenchidos', () => {
  for (const [field, value] of [['summary', 1], ['distance_km', '10'], ['duration_min', -1], ['map_url', 'javascript:alert(1)']]) {
    const event = fixture();
    event.itinerary[field] = value;
    assert.equal(run('Validar e deduplicar', { body: event })[0].json.valid, false);
  }
  for (const field of ['time', 'description']) {
    const event = fixture();
    event.itinerary.days[0].activities[0][field] = {};
    assert.equal(run('Validar e deduplicar', { body: event })[0].json.valid, false);
  }
});

test('e-mail ou telefone do canal escolhido continuam obrigatórios', () => {
  for (const channel of ['email', 'whatsapp']) {
    const event = fixture();
    event.channel = channel;
    event.recipient = { name: 'Viajante', email: null, phone: null };
    assert.equal(run('Validar e deduplicar', { body: event })[0].json.failureType, 'InvalidRecipient');
  }
});

for (const traceId of [undefined, null, '', '   ', '\t\n', 123]) {
  test(`trace inválido ${JSON.stringify(traceId)} produz fallback não vazio na DLQ`, () => {
    const event = fixture();
    event.trace_id = traceId;
    const invalid = run('Validar e deduplicar', { body: event })[0].json;
    assert.equal(invalid.valid, false);
    assert.equal(invalid.event.trace_id, 'unknown');
    const dlq = run('Montar DLQ', invalid)[0].json;
    assert.equal(dlq.trace_id, 'unknown');
  });
}

test('falha com trace válido mantém o código de rastreio', () => {
  const event = fixture();
  event.channel = 'invalid';
  assert.equal(run('Validar e deduplicar', { body: event })[0].json.event.trace_id, event.trace_id);
});

test('atividade sem horário ou descrição não gera espaço ou quebra extras', () => {
  const email = run('Montar email', { event: fixture() })[0].json;
  assert.match(email.html, /<strong>Parque Nacional de Sete Cidades<\/strong><\/p>/);
});

test('horário e descrição preenchidos continuam presentes e escapados', () => {
  const event = fixture();
  Object.assign(event.itinerary.days[0].activities[0], { time: '09:00', description: '<script>&"\'</script>' });
  const email = run('Montar email', { event })[0].json;
  assert.match(email.html, /<strong>09:00 Parque Nacional de Sete Cidades<\/strong><br>/);
  assert.ok(email.html.includes('&lt;script&gt;&amp;&quot;&#39;&lt;/script&gt;'));
  assert.doesNotMatch(email.html, /<script>/);
});

test('eventos só entram na janela dos últimos 50 após entrega bem-sucedida', () => {
  const event = fixture();
  const state = {};
  assert.equal(run('Validar e deduplicar', { body: event }, { state })[0].json.valid, true);
  assert.equal(state.sentEventIds, undefined);
  run('Registrar entrega', {}, { state, references: { 'Montar email': { event } } });
  assert.equal(run('Validar e deduplicar', { body: event }, { state }).length, 0);
  for (let i = 0; i < 60; i++) {
    run('Registrar entrega', {}, { state, references: { 'Montar email': { event: { ...event, event_id: String(i) } } } });
  }
  assert.equal(state.sentEventIds.length, 50);
  assert.equal(state.sentEventIds[0], '10');
});

test('resumo e descrição longos da IA são aceitos e preservados com escape HTML', () => {
  const event = fixture();
  const content = 'a'.repeat(5000) + '<script>&';
  event.itinerary.summary = content;
  event.itinerary.days[0].activities[0].description = content;
  assert.equal(run('Validar e deduplicar', { body: event })[0].json.valid, true);
  const email = run('Montar email', { event })[0].json;
  assert.equal(email.html.split('a'.repeat(5000) + '&lt;script&gt;&amp;').length - 1, 2);
  assert.doesNotMatch(email.html, /<script>/);
});

test('falhas de validação preservam o idioma suportado e usam fallback para idioma inválido', () => {
  for (const [language, expected] of [['en', 'en'], ['pt-BR', 'pt-BR'], [null, 'pt-BR'], ['invalid', 'pt-BR']]) {
    const event = fixture();
    event.language = language;
    event.recipient.email = 'invalid';
    const failure = run('Validar e deduplicar', { body: event })[0].json;
    assert.equal(failure.valid, false);
    assert.equal(run('Montar DLQ', failure)[0].json.request.language, expected);
  }
});

test('resumo ausente, nulo, vazio ou só espaços não gera parágrafo vazio', () => {
  for (const summary of [undefined, null, '', '   ']) {
    const event = fixture();
    event.itinerary.summary = summary;
    assert.doesNotMatch(run('Montar email', { event })[0].json.html, /<p style="line-height:1\.6">\s*<\/p>/);
  }
});

test('erro SMTP segue para DLQ sem expor erro bruto nem impedir retentativa', () => {
  const event = fixture();
  event.language = 'en';
  const state = {};
  const smtp = workflow.nodes.find((node) => node.name === 'Enviar email SMTP');
  assert.equal(smtp.onError, 'continueErrorOutput');
  assert.equal(workflow.connections[smtp.name].main[1][0].node, 'Falha email');
  assert.equal(workflow.connections['Falha email'].main[0][0].node, 'Montar DLQ');
  const failure = run('Falha email', { error: 'provider-secret fixture@example.invalid' }, {
    state, references: { 'Montar email': { event } },
  })[0].json;
  const dlq = run('Montar DLQ', failure, { state })[0].json;
  assert.equal(dlq.error.type, 'EmailDeliveryFailed');
  assert.equal(dlq.trace_id, event.trace_id);
  assert.equal(dlq.request.language, 'en');
  assert.doesNotMatch(JSON.stringify(dlq), /provider-secret|fixture@example\.invalid/);
  assert.equal(state.sentEventIds, undefined);
  assert.equal(run('Validar e deduplicar', { body: event }, { state })[0].json.valid, true);
});
