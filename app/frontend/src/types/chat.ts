/** Tipos do chat com IA — definidos por P4 na issue #12 (T0016). */

export type PapelMensagemChat = 'user' | 'assistant';

export interface MensagemChat {
  role: PapelMensagemChat;
  content: string;
}

export interface ItineraryActivity {
  time?: string;
  title: string;
  description?: string;
}

export interface ItineraryDay {
  day: number;
  activities: ItineraryActivity[];
}

export interface Itinerary {
  trip_id: string;
  title: string;
  origin: string;
  destination: string;
  distance_km?: number;
  duration_min?: number;
  summary?: string;
  days: ItineraryDay[];
  map_url?: string;
}

export interface RequisicaoChat {
  messages: MensagemChat[];
  origin: string;
  destination: string;
}

export interface RespostaChat {
  reply: string;
  done: boolean;
  itinerary: Itinerary | null;
}

export const MAX_CHAT_MESSAGES = 12;
export const MAX_CHAT_MESSAGE_LENGTH = 1000;
export const MAX_CHAT_LOCATION_LENGTH = 100;
