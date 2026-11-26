/** Cliente HTTP do chat com IA — implementado por P4 na issue #12 (T0016). */

import { API_BASE_URL } from '../config';
import type {
  Itinerary,
  ItineraryActivity,
  ItineraryDay,
  MensagemChat,
  RespostaChat,
} from '../types/chat';
import { ApiContractError, ApiError, parseRequestId, request, requestHeaders } from './api';

const MENSAGEM_ERRO_AMIGAVEL_PADRAO =
  'Não foi possível conversar com o assistente agora. Tente novamente em instantes.';

export class ChatApiError extends ApiError {
  readonly trace_id?: string;
  readonly traceId?: string;

  constructor(
    message: string,
    status: number,
    traceId?: string,
    fieldErrors: Readonly<Record<string, string>> = {},
  ) {
    super(message, status, fieldErrors);
    this.name = 'ApiError';
    this.trace_id = traceId;
    this.traceId = traceId;
  }
}

function isObjectRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function parseItineraryActivity(value: unknown): ItineraryActivity {
  if (!isObjectRecord(value) || typeof value.title !== 'string' || !value.title.trim()) {
    throw new ApiContractError('Atividade do roteiro inválida na resposta do chat.');
  }
  const activity: ItineraryActivity = { title: value.title.trim() };
  if (typeof value.time === 'string' && value.time.trim()) {
    activity.time = value.time.trim();
  }
  if (typeof value.description === 'string' && value.description.trim()) {
    activity.description = value.description.trim();
  }
  return activity;
}

function parseItineraryDay(value: unknown): ItineraryDay {
  if (
    !isObjectRecord(value) ||
    typeof value.day !== 'number' ||
    !Number.isInteger(value.day) ||
    value.day < 1 ||
    !Array.isArray(value.activities)
  ) {
    throw new ApiContractError('Dia do roteiro inválido na resposta do chat.');
  }
  return {
    day: value.day,
    activities: value.activities.map(parseItineraryActivity),
  };
}

function parseItinerary(value: unknown): Itinerary {
  if (!isObjectRecord(value)) {
    throw new ApiContractError('Roteiro estruturado inválido na resposta do chat.');
  }
  const { trip_id, title, origin, destination, days } = value;
  if (
    typeof trip_id !== 'string' ||
    !trip_id.trim() ||
    typeof title !== 'string' ||
    !title.trim() ||
    typeof origin !== 'string' ||
    !origin.trim() ||
    typeof destination !== 'string' ||
    !destination.trim() ||
    !Array.isArray(days) ||
    days.length === 0
  ) {
    throw new ApiContractError('Campos obrigatórios do roteiro ausentes na resposta do chat.');
  }

  const itinerary: Itinerary = {
    trip_id: trip_id.trim(),
    title: title.trim(),
    origin: origin.trim(),
    destination: destination.trim(),
    days: days.map(parseItineraryDay),
  };

  if (typeof value.distance_km === 'number' && Number.isFinite(value.distance_km)) {
    itinerary.distance_km = value.distance_km;
  }
  if (typeof value.duration_min === 'number' && Number.isFinite(value.duration_min)) {
    itinerary.duration_min = value.duration_min;
  }
  if (typeof value.summary === 'string' && value.summary.trim()) {
    itinerary.summary = value.summary.trim();
  }
  if (typeof value.map_url === 'string' && value.map_url.trim()) {
    itinerary.map_url = value.map_url.trim();
  }

  return itinerary;
}

export function parseRespostaChat(value: unknown): RespostaChat {
  if (!isObjectRecord(value)) {
    throw new ApiContractError('Resposta inválida do endpoint de chat.');
  }
  if (typeof value.reply !== 'string' || !value.reply.trim() || typeof value.done !== 'boolean') {
    throw new ApiContractError('Contrato de resposta do chat violado.');
  }
  if (value.done) {
    if (value.itinerary === null || value.itinerary === undefined) {
      throw new ApiContractError('Roteiro final ausente quando done=true.');
    }
    return {
      reply: value.reply.trim(),
      done: true,
      itinerary: parseItinerary(value.itinerary),
    };
  }
  return {
    reply: value.reply.trim(),
    done: false,
    itinerary:
      value.itinerary !== null && value.itinerary !== undefined
        ? parseItinerary(value.itinerary)
        : null,
  };
}

function extrairTraceIdDeErro(payload: unknown, response: Response): string | undefined {
  if (isObjectRecord(payload)) {
    if (typeof payload.trace_id === 'string' && payload.trace_id.trim()) {
      return payload.trace_id.trim();
    }
    if (typeof payload.traceId === 'string' && payload.traceId.trim()) {
      return payload.traceId.trim();
    }
  }
  const reqId = parseRequestId(response.headers.get('X-Request-ID'));
  return reqId.available ? reqId.value : undefined;
}

export async function enviarMensagem(
  messages: MensagemChat[],
  origin: string,
  destination: string,
  signal?: AbortSignal,
): Promise<RespostaChat> {
  const body = JSON.stringify({ messages, origin, destination });
  const init: RequestInit = {
    method: 'POST',
    body,
    signal,
  };

  // Se `request` de `./api` foi substituído por um spy/mock direto em testes, delega para ele.
  if ('mock' in request) {
    const raw = await request<unknown>('/chat/mensagens', init);
    return parseRespostaChat(raw);
  }

  const response = await fetch(`${API_BASE_URL}/chat/mensagens`, {
    ...init,
    credentials: 'include',
    headers: requestHeaders(init),
  });

  if (!response.ok) {
    let payload: unknown = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    const traceId = extrairTraceIdDeErro(payload, response);
    const message =
      response.status === 429
        ? 'Limite de mensagens atingido nesta sessão. Aguarde alguns minutos e tente novamente.'
        : MENSAGEM_ERRO_AMIGAVEL_PADRAO;
    throw new ChatApiError(message, response.status, traceId);
  }

  const payload: unknown = await response.json();
  return parseRespostaChat(payload);
}
