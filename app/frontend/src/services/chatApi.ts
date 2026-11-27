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

export function mensagemAmigavelPorStatus(status: number): string {
  if (status === 401) {
    return 'Sua sessão expirou ou não está autenticada. Entre novamente para conversar com o assistente.';
  }
  if (status === 422) {
    return 'Verifique os limites da mensagem (até 1000 caracteres e 12 mensagens) e os campos de origem e destino.';
  }
  if (status === 429) {
    return 'Limite de mensagens atingido nesta sessão. Aguarde alguns minutos e tente novamente.';
  }
  return MENSAGEM_ERRO_AMIGAVEL_PADRAO;
}

export type IdiomaChat = 'pt-BR' | 'en' | 'es' | 'fr' | 'zh-CN' | 'hi' | 'ar' | 'ru';

interface TemplatesContingenciaChat {
  step1: string;
  step2: string;
  step3: string;
  done: (origin: string, destination: string) => string;
  title: (origin: string, destination: string) => string;
  summary: (origin: string, destination: string) => string;
  act1Title: (destination: string) => string;
  act1Desc: string;
  act2Title: (destination: string) => string;
  act2Desc: string;
  act3Title: (destination: string) => string;
  act3Desc: string;
}

const TEMPLATES_CONTINGENCIA_POR_IDIOMA: Record<IdiomaChat, TemplatesContingenciaChat> = {
  'pt-BR': {
    step1:
      'Qual ritmo você prefere para a viagem (tranquilo, moderado ou intenso) para começarmos a montar seu roteiro?',
    step2:
      'Perfeito! Quem serão os acompanhantes da viagem (sozinho, casal, família com crianças ou amigos)?',
    step3:
      'Ótimo! Quais são suas preferências e restrições de gastronomia para incluirmos no roteiro?',
    done: (origin, destination) =>
      `Com base nas suas escolhas de ritmo, acompanhantes e gastronomia, montei seu roteiro de ${origin} para ${destination}.`,
    title: (origin, destination) => `Roteiro ${origin} a ${destination}`,
    summary: (origin, destination) =>
      `Roteiro personalizado de ${origin} para ${destination} considerando ritmo, acompanhantes e gastronomia local.`,
    act1Title: (destination) => `Centro histórico e atrativos principais de ${destination}`,
    act1Desc:
      'Passeio inicial pelos pontos culturais e patrimônios locais (confirme horários no destino).',
    act2Title: (destination) => `Gastronomia regional em ${destination}`,
    act2Desc: 'Refeição com pratos típicos locais respeitando suas preferências e restrições.',
    act3Title: (destination) => `Passeio ao ar livre e mirantes de ${destination}`,
    act3Desc: 'Atividade adaptada ao ritmo escolhido e ao perfil dos acompanhantes.',
  },
  en: {
    step1:
      'What travel pace do you prefer (relaxed, moderate, or intense) so we can start building your itinerary?',
    step2:
      'Great! Who will be traveling with you (solo, couple, family with children, or friends)?',
    step3:
      'Awesome! What are your food preferences and dietary restrictions to include in the itinerary?',
    done: (origin, destination) =>
      `Based on your travel pace, companions, and food preferences, I created your itinerary from ${origin} to ${destination}.`,
    title: (origin, destination) => `Itinerary ${origin} to ${destination}`,
    summary: (origin, destination) =>
      `Personalized itinerary from ${origin} to ${destination} tailored to your pace, companions, and local cuisine.`,
    act1Title: (destination) => `Historic center and main landmarks of ${destination}`,
    act1Desc:
      'Morning walk around local cultural heritage sites (please confirm opening hours locally).',
    act2Title: (destination) => `Regional cuisine in ${destination}`,
    act2Desc: 'Lunch featuring traditional local dishes matching your dietary preferences.',
    act3Title: (destination) => `Outdoor sightseeing in ${destination}`,
    act3Desc: 'Afternoon activity adapted to your chosen travel pace and companions.',
  },
  es: {
    step1:
      '¿Qué ritmo prefieres para el viaje (tranquilo, moderado o intenso) para empezar a armar tu itinerario?',
    step2: '¡Perfecto! ¿Quiénes serán tus acompañantes (solo, pareja, familia con niños o amigos)?',
    step3:
      '¡Genial! ¿Cuáles son tus preferencias y restricciones gastronómicas para incluir en el itinerario?',
    done: (origin, destination) =>
      `Según tu ritmo, acompañantes y preferencias gastronómicas, preparé tu itinerario de ${origin} a ${destination}.`,
    title: (origin, destination) => `Itinerario ${origin} a ${destination}`,
    summary: (origin, destination) =>
      `Itinerario personalizado de ${origin} a ${destination} adaptado a tu ritmo, acompañantes y cocina local.`,
    act1Title: (destination) => `Centro histórico y atractivos principales de ${destination}`,
    act1Desc:
      'Recorrido inicial por sitios culturales y patrimonios locales (confirma horarios localmente).',
    act2Title: (destination) => `Gastronomía regional en ${destination}`,
    act2Desc: 'Almuerzo con platos típicos locales según tus preferencias y restricciones.',
    act3Title: (destination) => `Paseo al aire libre y miradores de ${destination}`,
    act3Desc: 'Actividad de tarde adaptada al ritmo elegido y a los acompañantes.',
  },
  fr: {
    step1:
      'Quel rythme préférez-vous pour le voyage (calme, modéré ou intense) pour commencer votre itinéraire ?',
    step2:
      'Parfait ! Qui vous accompagne pendant le voyage (seul, en couple, famille avec enfants ou amis) ?',
    step3:
      'Très bien ! Quelles sont vos préférences et restrictions gastronomiques à inclure dans le voyage ?',
    done: (origin, destination) =>
      `Selon votre rythme, vos accompagnants et vos préférences culinaires, voici votre itinéraire de ${origin} à ${destination}.`,
    title: (origin, destination) => `Itinéraire ${origin} à ${destination}`,
    summary: (origin, destination) =>
      `Itinéraire personnalisé de ${origin} à ${destination} adapté à votre rythme, vos accompagnants et la gastronomie locale.`,
    act1Title: (destination) => `Centre historique et sites principaux de ${destination}`,
    act1Desc:
      'Visite matinale des patrimoines culturels locaux (veuillez confirmer les horaires sur place).',
    act2Title: (destination) => `Gastronomie régionale à ${destination}`,
    act2Desc: 'Repas de spécialités locales respectant vos préférences alimentaires.',
    act3Title: (destination) => `Promenade en plein air à ${destination}`,
    act3Desc: "Activité d'après-midi adaptée au rythme choisi et à vos accompagnants.",
  },
  'zh-CN': {
    step1: '您希望本次旅行的节奏是怎样的（轻松、适中还是紧凑），以便我们开始规划行程？',
    step2: '好的！请问您的同行人员有哪些（独自、情侣、带孩家庭还是朋友）？',
    step3: '太好了！请问您有哪些饮食偏好或忌口需要安排进行程中？',
    done: (origin, destination) =>
      `根据您的旅行节奏、同行人员和饮食偏好，我已为您定制从 ${origin} 到 ${destination} 的行程。`,
    title: (origin, destination) => `${origin} 至 ${destination} 行程`,
    summary: (origin, destination) =>
      `从 ${origin} 到 ${destination} 的定制行程，兼顾旅行节奏、同行人员与当地美食。`,
    act1Title: (destination) => `${destination} 历史中心与主要景点`,
    act1Desc: '上午游览当地文化遗产景点（请在当地确认开放时间）。',
    act2Title: (destination) => `${destination} 地方特色美食`,
    act2Desc: '根据您的饮食偏好品尝当地传统菜肴。',
    act3Title: (destination) => `${destination} 户外游览`,
    act3Desc: '结合所选旅行节奏与同行人员安排的下午休闲活动。',
  },
  hi: {
    step1: 'अपनी यात्रा योजना शुरू करने के लिए आप कौन-सी गति पसंद करेंगे (शांत, मध्यम या तेज़)?',
    step2: 'बहुत बढ़िया! यात्रा में आपके साथ कौन रहेगा (अकेले, युगल, बच्चों के साथ परिवार या मित्र)?',
    step3: 'शानदार! भोजन के लिए आपकी प्राथमिकताएँ और परहेज़ क्या हैं जिन्हें यात्रा कार्यक्रम में शामिल किया जाए?',
    done: (origin, destination) =>
      `आपकी यात्रा गति, साथियों और भोजन प्राथमिकताओं के आधार पर ${origin} से ${destination} के लिए यात्रा कार्यक्रम तैयार है।`,
    title: (origin, destination) => `${origin} से ${destination} यात्रा कार्यक्रम`,
    summary: (origin, destination) =>
      `${origin} से ${destination} के लिए गति, साथियों और स्थानीय व्यंजनों के अनुसार व्यक्तिगत यात्रा योजना।`,
    act1Title: (destination) => `${destination} का ऐतिहासिक केंद्र और प्रमुख आकर्षण`,
    act1Desc: 'स्थानीय सांस्कृतिक धरोहरों का भ्रमण (कृपया स्थानीय स्तर पर समय की पुष्टि करें)।',
    act2Title: (destination) => `${destination} का क्षेत्रीय व्यंजन`,
    act2Desc: 'आपकी आहार प्राथमिकताओं के अनुसार पारंपरिक स्थानीय भोजन।',
    act3Title: (destination) => `${destination} में आउटडोर भ्रमण`,
    act3Desc: 'चुनी गई यात्रा गति और साथियों के अनुकूल दोपहर की गतिविधि।',
  },
  ar: {
    step1: 'ما وتيرة الرحلة التي تفضلها (هادئة، معتدلة أم مكثفة) لنبدأ إعداد برنامج رحلتك؟',
    step2: 'رائع! من سيرافقك في الرحلة (بمفردك، زوجان، عائلة مع أطفال أم أصدقاء)؟',
    step3: 'ممتاز! ما هي تفضيلاتك وقيودك الغذائية لإدراجها في برنامج الرحلة؟',
    done: (origin, destination) =>
      `بناءً على وتيرة الرحلة والمرافقين وتفضيلات الطعام، أعددت برنامج رحلتك من ${origin} إلى ${destination}.`,
    title: (origin, destination) => `برنامج رحلة من ${origin} إلى ${destination}`,
    summary: (origin, destination) =>
      `برنامج رحلة مخصص من ${origin} إلى ${destination} يراعي وتيرة السفر والمرافقين والمأكولات المحلية.`,
    act1Title: (destination) => `المركز التاريخي والمعالم الرئيسية في ${destination}`,
    act1Desc: 'جولة صباحية في مواقع التراث الثقافي المحلي (يرجى تأكيد المواعيد محليًا).',
    act2Title: (destination) => `المأكولات الإقليمية في ${destination}`,
    act2Desc: 'وجبة من الأطباق التقليدية المحلية وفق تفضيلاتك الغذائية.',
    act3Title: (destination) => `جولة خارجية في ${destination}`,
    act3Desc: 'نشاط بعد الظهر متوافق مع وتيرة السفر والمرافقين.',
  },
  ru: {
    step1:
      'Какой темп поездки вы предпочитаете (спокойный, умеренный или интенсивный), чтобы начать составление маршрута?',
    step2: 'Отлично! С кем вы планируете путешествовать (один, пара, семья с детьми или друзья)?',
    step3:
      'Замечательно! Какие у вас кулинарные предпочтения и ограничения в питании для маршрута?',
    done: (origin, destination) =>
      `С учетом вашего темпа поездки, попутчиков и кулинарных предпочтений я составил маршрут из ${origin} в ${destination}.`,
    title: (origin, destination) => `Маршрут ${origin} — ${destination}`,
    summary: (origin, destination) =>
      `Персональный маршрут из ${origin} в ${destination} с учетом темпа поездки, попутчиков и местной кухни.`,
    act1Title: (destination) => `Исторический центр и главные достопримечательности ${destination}`,
    act1Desc: 'Утренняя прогулка по объектам культурного наследия (уточняйте расписание на месте).',
    act2Title: (destination) => `Региональная кухня в ${destination}`,
    act2Desc: 'Обед с традиционными местными блюдами с учетом ваших предпочтений.',
    act3Title: (destination) => `Прогулка на свежем воздухе в ${destination}`,
    act3Desc: 'Дневная активность, адаптированная под выбранный темп поездки и компанию.',
  },
};

const PALAVRAS_EN = new Set([
  'hello',
  'hi',
  'hey',
  'want',
  'trip',
  'travel',
  'itinerary',
  'plan',
  'planning',
  'relaxed',
  'moderate',
  'intense',
  'pace',
  'solo',
  'couple',
  'family',
  'children',
  'kids',
  'friends',
  'food',
  'cuisine',
  'dietary',
  'restrictions',
  'preferences',
  'please',
  'thank',
  'thanks',
  'with',
  'without',
  'would',
  'like',
  'for',
  'from',
  'the',
  'and',
  'my',
  'we',
  'our',
  'guide',
  'visit',
  'going',
  'traveling',
  'travelling',
]);

const PALAVRAS_ES = new Set([
  'hola',
  'quiero',
  'viaje',
  'viajar',
  'itinerario',
  'planear',
  'planificar',
  'pareja',
  'familia',
  'ninos',
  'niños',
  'amigos',
  'solo',
  'gastronomia',
  'gastronomía',
  'comida',
  'gracias',
  'favor',
  'con',
  'sin',
  'para',
  'ritmo',
  'tranquilo',
  'moderado',
  'intenso',
  'vamos',
  'viajamos',
  'restricciones',
  'preferencias',
  'buenos',
  'dias',
  'días',
  'buenas',
  'tardes',
  'nuestro',
  'nuestra',
  'uno',
  'una',
  'del',
  'los',
  'las',
]);

const PALAVRAS_FR = new Set([
  'bonjour',
  'salut',
  'bonsoir',
  'je',
  'veux',
  'voudrais',
  'voyage',
  'voyager',
  'itineraire',
  'itinéraire',
  'planifier',
  'calme',
  'modere',
  'modéré',
  'intense',
  'seul',
  'couple',
  'famille',
  'enfants',
  'amis',
  'cuisine',
  'gastronomie',
  'merci',
  'avec',
  'sans',
  'pour',
  'nous',
  'notre',
  'rythme',
  'preferences',
  'préférences',
  'restrictions',
  'repas',
  'visiter',
  'les',
  'des',
  'une',
]);

const PALAVRAS_PT = new Set([
  'ola',
  'olá',
  'oi',
  'quero',
  'viagem',
  'viajar',
  'roteiro',
  'planejar',
  'montar',
  'ritmo',
  'tranquilo',
  'moderado',
  'intenso',
  'sozinho',
  'sozinha',
  'casal',
  'familia',
  'família',
  'criancas',
  'crianças',
  'amigos',
  'gastronomia',
  'culinaria',
  'culinária',
  'comida',
  'obrigado',
  'obrigada',
  'com',
  'sem',
  'para',
  'preferencias',
  'preferências',
  'restricoes',
  'restrições',
  'gostamos',
  'vamos',
  'prefiro',
  'vou',
  'nos',
  'nós',
  'meu',
  'minha',
  'um',
  'uma',
]);

function detectarIdiomaTexto(texto: string): IdiomaChat | null {
  const limpo = texto.trim();
  if (!limpo) return null;

  // Scripts não-latinos: detecção exata por faixa Unicode.
  if (/[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]/.test(limpo)) return 'ar';
  if (/[\u4E00-\u9FFF]/.test(limpo)) return 'zh-CN';
  if (/[\u0900-\u097F]/.test(limpo)) return 'hi';
  if (/[\u0400-\u04FF]/.test(limpo)) return 'ru';

  const minusculo = limpo.toLowerCase();
  const tokens = minusculo.match(/\p{L}+/gu) ?? [];
  if (tokens.length === 0) return null;

  let pontosEn = 0;
  let pontosEs = 0;
  let pontosFr = 0;
  let pontosPt = 0;

  if (/[¿¡ñ]/.test(minusculo)) pontosEs += 3;
  if (/[ãõ]/.test(minusculo)) pontosPt += 3;
  if (/(?:\b[jldmtnsc]'|œ|[èêëîïûù])/.test(minusculo)) pontosFr += 2;

  for (const token of tokens) {
    if (PALAVRAS_EN.has(token)) pontosEn += 2;
    if (PALAVRAS_ES.has(token)) pontosEs += 2;
    if (PALAVRAS_FR.has(token)) pontosFr += 2;
    if (PALAVRAS_PT.has(token)) pontosPt += 2;
  }

  const candidatos: Array<{ idioma: IdiomaChat; pontos: number }> = [
    { idioma: 'pt-BR', pontos: pontosPt },
    { idioma: 'en', pontos: pontosEn },
    { idioma: 'es', pontos: pontosEs },
    { idioma: 'fr', pontos: pontosFr },
  ];

  candidatos.sort((a, b) => b.pontos - a.pontos);
  const melhor = candidatos[0];
  const segundo = candidatos[1];
  if (melhor.pontos === 0 || melhor.pontos === segundo.pontos) {
    return null;
  }
  return melhor.idioma;
}

/**
 * Detecta o idioma em que o usuário está digitando no chat (entre os 8 idiomas de i18n.md).
 * Avalia da mensagem mais recente para a mais antiga para manter consistência quando
 * o usuário envia respostas curtas/neutras (ex.: "ok", "2").
 */
export function detectarIdiomaMensagem(messages: MensagemChat[]): IdiomaChat {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const msg = messages[i];
    if (msg.role !== 'user') continue;
    const detectado = detectarIdiomaTexto(msg.content);
    if (detectado) {
      return detectado;
    }
  }
  return 'pt-BR';
}

/**
 * Fixture local da issue #11/#12 (3 perguntas guiadas + roteiro final do contrato).
 * Acionado automaticamente apenas quando o backend em execução retorna HTTP 404
 * em POST /api/v1/chat/mensagens (ou seja, quando a branch de frontend #31 é
 * executada isoladamente antes do merge do backend #30 em development).
 */
export function gerarRespostaContingenciaLocal(
  messages: MensagemChat[],
  origin: string,
  destination: string,
  idiomaExplicito?: IdiomaChat,
): RespostaChat {
  const origemLimpa = origin.trim() || 'Teresina - PI';
  const destinoLimpo = destination.trim() || 'Piripiri - PI';
  const idioma = idiomaExplicito ?? detectarIdiomaMensagem(messages);
  const tpl =
    TEMPLATES_CONTINGENCIA_POR_IDIOMA[idioma] ?? TEMPLATES_CONTINGENCIA_POR_IDIOMA['pt-BR'];
  const trocasUsuario = messages.filter((msg) => msg.role === 'user').length;

  if (trocasUsuario <= 1) {
    return {
      reply: tpl.step1,
      done: false,
      itinerary: null,
    };
  }
  if (trocasUsuario === 2) {
    return {
      reply: tpl.step2,
      done: false,
      itinerary: null,
    };
  }
  if (trocasUsuario === 3) {
    return {
      reply: tpl.step3,
      done: false,
      itinerary: null,
    };
  }

  return {
    reply: tpl.done(origemLimpa, destinoLimpo),
    done: true,
    itinerary: {
      trip_id: 'trip-chat-contingencia-001',
      title: tpl.title(origemLimpa, destinoLimpo),
      origin: origemLimpa,
      destination: destinoLimpo,
      summary: tpl.summary(origemLimpa, destinoLimpo),
      days: [
        {
          day: 1,
          activities: [
            {
              time: '09:00',
              title: tpl.act1Title(destinoLimpo),
              description: tpl.act1Desc,
            },
            {
              time: '12:30',
              title: tpl.act2Title(destinoLimpo),
              description: tpl.act2Desc,
            },
            {
              time: '15:30',
              title: tpl.act3Title(destinoLimpo),
              description: tpl.act3Desc,
            },
          ],
        },
      ],
      map_url: `https://www.google.com/maps/dir/?api=1&origin=${encodeURIComponent(origemLimpa)}&destination=${encodeURIComponent(destinoLimpo)}`,
    },
  };
}

export async function enviarMensagem(
  messages: MensagemChat[],
  origin: string,
  destination: string,
  signal?: AbortSignal,
): Promise<RespostaChat> {
  const idiomaDetectado = detectarIdiomaMensagem(messages);
  const body = JSON.stringify({ messages, origin, destination });
  const headers = requestHeaders({ method: 'POST', body });
  if (!headers.has('Accept-Language')) {
    headers.set('Accept-Language', idiomaDetectado);
  }
  const init: RequestInit = {
    method: 'POST',
    body,
    signal,
    headers,
  };

  // Se `request` de `./api` foi substituído por um spy/mock direto em testes, delega para ele.
  if ('mock' in request) {
    try {
      const raw = await request<unknown>('/chat/mensagens', init);
      return parseRespostaChat(raw);
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 404) {
        return gerarRespostaContingenciaLocal(messages, origin, destination, idiomaDetectado);
      }
      if (err instanceof ChatApiError) {
        throw err;
      }
      if (err instanceof ApiError) {
        const traceId =
          typeof (err as unknown as Record<string, unknown>).trace_id === 'string'
            ? String((err as unknown as Record<string, unknown>).trace_id)
            : typeof (err as unknown as Record<string, unknown>).traceId === 'string'
              ? String((err as unknown as Record<string, unknown>).traceId)
              : undefined;
        throw new ChatApiError(
          mensagemAmigavelPorStatus(err.status),
          err.status,
          traceId,
          err.fieldErrors,
        );
      }
      throw err;
    }
  }

  const response = await fetch(`${API_BASE_URL}/chat/mensagens`, {
    ...init,
    credentials: 'include',
    headers,
  });

  if (response.status === 404) {
    return gerarRespostaContingenciaLocal(messages, origin, destination, idiomaDetectado);
  }

  if (!response.ok) {
    let payload: unknown = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    const traceId = extrairTraceIdDeErro(payload, response);
    throw new ChatApiError(mensagemAmigavelPorStatus(response.status), response.status, traceId);
  }

  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    const reqId = parseRequestId(response.headers.get('X-Request-ID'));
    throw new ChatApiError(
      MENSAGEM_ERRO_AMIGAVEL_PADRAO,
      response.status,
      reqId.available ? reqId.value : undefined,
    );
  }
  return parseRespostaChat(payload);
}
