/** Tela de diálogo com a IA para montar o roteiro — implementada por P4 na issue #12 (T0016). */

import type { ComponentType, FormEvent, KeyboardEvent } from 'react';
import { useEffect, useId, useRef, useState } from 'react';

import { ChatApiError, enviarMensagem } from '../services/chatApi';
import type { Itinerary, MensagemChat } from '../types/chat';
import {
  MAX_CHAT_LOCATION_LENGTH,
  MAX_CHAT_MESSAGE_LENGTH,
  MAX_CHAT_MESSAGES,
} from '../types/chat';
import { EnvioRoteiro } from './EnvioRoteiro';
import { ErroAmigavel } from './ErroAmigavel';

const ORIGEM_PADRAO = 'Teresina - PI';
const DESTINO_PADRAO = 'Piripiri - PI';
const MENSAGEM_ERRO_PADRAO_CHAT =
  'Algo deu errado ao conversar com o assistente. Não foi possível concluir sua solicitação agora.';

interface ErroChatEstado {
  mensagem: string;
  traceId?: string;
}

export interface ChatIAProps {
  /** Permite sobrescrever a detecção automática de disponibilidade do EnvioRoteiro em testes. */
  envioRoteiroDisponivel?: boolean;
}

const EnvioRoteiroJSX = EnvioRoteiro as unknown as ComponentType<{
  itinerary: Itinerary;
  onSent?: () => void;
}>;

const ErroAmigavelJSX = ErroAmigavel as unknown as ComponentType<{
  traceId?: string;
  mensagem?: string;
  onTentarNovamente?: () => void;
}>;

function isComponenteImplementado(componente: unknown): boolean {
  if (typeof componente === 'object' && componente !== null) {
    return true;
  }
  if (typeof componente !== 'function') {
    return false;
  }
  const fonte = Function.prototype.toString.call(componente).replace(/\s+/g, ' ');
  return !/\{\s*return\s+null;?\s*\}$/.test(fonte);
}

function isUrlHttpSegura(url: string | undefined): boolean {
  if (!url) return false;
  try {
    const parsed = new URL(url);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
}

function lerOrigemDestinoFormularioPrincipal(): { origin: string; destination: string } {
  if (typeof document === 'undefined') {
    return { origin: ORIGEM_PADRAO, destination: DESTINO_PADRAO };
  }
  const origemCidade =
    document.querySelector<HTMLInputElement>('#origem_cidade')?.value?.trim() ?? '';
  const origemUf = document.querySelector<HTMLSelectElement>('#origem_uf')?.value?.trim() ?? '';
  const destinoCidade =
    document.querySelector<HTMLInputElement>('#destino_cidade')?.value?.trim() ?? '';
  const destinoUf = document.querySelector<HTMLSelectElement>('#destino_uf')?.value?.trim() ?? '';

  const origin = origemCidade
    ? origemUf
      ? `${origemCidade} - ${origemUf}`
      : origemCidade
    : ORIGEM_PADRAO;
  const destination = destinoCidade
    ? destinoUf
      ? `${destinoCidade} - ${destinoUf}`
      : destinoCidade
    : DESTINO_PADRAO;

  return {
    origin: origin.slice(0, MAX_CHAT_LOCATION_LENGTH),
    destination: destination.slice(0, MAX_CHAT_LOCATION_LENGTH),
  };
}

function extrairTraceIdDeExcecao(err: unknown): string | undefined {
  if (err && typeof err === 'object') {
    const registro = err as Record<string, unknown>;
    if (typeof registro.trace_id === 'string' && registro.trace_id.trim()) {
      return registro.trace_id.trim();
    }
    if (typeof registro.traceId === 'string' && registro.traceId.trim()) {
      return registro.traceId.trim();
    }
  }
  return undefined;
}

export function ChatIA({ envioRoteiroDisponivel: envioRoteiroProp }: ChatIAProps = {}) {
  const idBase = useId();
  const inputMensagemId = `${idBase}-mensagem`;
  const inputOrigemId = `${idBase}-origem`;
  const inputDestinoId = `${idBase}-destino`;
  const statusLimiteId = `${idBase}-status-limite`;

  const [messages, setMessages] = useState<MensagemChat[]>([]);
  const [inputText, setInputText] = useState('');
  const [origin, setOrigin] = useState(ORIGEM_PADRAO);
  const [destination, setDestination] = useState(DESTINO_PADRAO);
  const [origemEditadaManual, setOrigemEditadaManual] = useState(false);
  const [destinoEditadoManual, setDestinoEditadoManual] = useState(false);
  const [isSending, setIsSending] = useState(false);
  const [done, setDone] = useState(false);
  const [itinerary, setItinerary] = useState<Itinerary | null>(null);
  const [erro, setErro] = useState<ErroChatEstado | null>(null);
  const [mostrarModalEnvio, setMostrarModalEnvio] = useState(false);
  const [copiado, setCopiado] = useState(false);

  const inputRef = useRef<HTMLInputElement | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const deveFocarAposEnvioRef = useRef(false);

  useEffect(() => {
    const sincronizarComFormulario = () => {
      const doFormulario = lerOrigemDestinoFormularioPrincipal();
      if (!origemEditadaManual) {
        setOrigin(doFormulario.origin);
      }
      if (!destinoEditadoManual) {
        setDestination(doFormulario.destination);
      }
    };

    sincronizarComFormulario();
    if (typeof document === 'undefined') {
      return undefined;
    }

    const seletores = ['#origem_cidade', '#origem_uf', '#destino_cidade', '#destino_uf'];
    const elementos = seletores
      .map((seletor) => document.querySelector<HTMLElement>(seletor))
      .filter((el): el is HTMLElement => el !== null);

    for (const el of elementos) {
      el.addEventListener('input', sincronizarComFormulario);
      el.addEventListener('change', sincronizarComFormulario);
    }

    return () => {
      for (const el of elementos) {
        el.removeEventListener('input', sincronizarComFormulario);
        el.removeEventListener('change', sincronizarComFormulario);
      }
    };
  }, [origemEditadaManual, destinoEditadoManual]);

  useEffect(() => {
    if (!isSending && deveFocarAposEnvioRef.current) {
      deveFocarAposEnvioRef.current = false;
      inputRef.current?.focus();
    }
  }, [isSending, messages.length, erro]);

  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort();
    };
  }, []);

  // Garante sempre vaga para o par [usuário, assistente] dentro do teto de 12 mensagens.
  const limiteMensagensAtingido = messages.length >= MAX_CHAT_MESSAGES - 1;
  const limiteCaracteresExcedido = inputText.length > MAX_CHAT_MESSAGE_LENGTH;
  const textoLimpo = inputText.trim();
  const envioDesabilitado =
    isSending ||
    textoLimpo.length === 0 ||
    limiteMensagensAtingido ||
    limiteCaracteresExcedido ||
    origin.trim().length === 0 ||
    destination.trim().length === 0;

  // Enquanto EnvioRoteiro (P5, #15) for o stub que retorna null do PR 0, o botão fica desabilitado com title="Em breve".
  const envioRoteiroDisponivel =
    typeof envioRoteiroProp === 'boolean'
      ? envioRoteiroProp
      : isComponenteImplementado(EnvioRoteiro);
  const erroAmigavelImplementado = isComponenteImplementado(ErroAmigavel);

  async function submeterMensagem(textoParaEnviar: string) {
    const conteudo = textoParaEnviar.trim();
    if (
      !conteudo ||
      isSending ||
      messages.length >= MAX_CHAT_MESSAGES - 1 ||
      conteudo.length > MAX_CHAT_MESSAGE_LENGTH
    ) {
      return;
    }

    const doFormulario = lerOrigemDestinoFormularioPrincipal();
    const origemEfetiva =
      (origemEditadaManual ? origin : doFormulario.origin).trim() || ORIGEM_PADRAO;
    const destinoEfetivo =
      (destinoEditadoManual ? destination : doFormulario.destination).trim() || DESTINO_PADRAO;
    if (!origemEditadaManual && origemEfetiva !== origin) {
      setOrigin(origemEfetiva);
    }
    if (!destinoEditadoManual && destinoEfetivo !== destination) {
      setDestination(destinoEfetivo);
    }

    const historicoAnterior = messages;
    const novaMensagemUsuario: MensagemChat = {
      role: 'user',
      content: conteudo,
    };
    const proximoHistorico = [...historicoAnterior, novaMensagemUsuario];

    setMessages(proximoHistorico);
    setInputText('');
    setErro(null);
    setCopiado(false);
    setIsSending(true);
    deveFocarAposEnvioRef.current = true;

    abortControllerRef.current?.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const resposta = await enviarMensagem(
        proximoHistorico,
        origemEfetiva,
        destinoEfetivo,
        controller.signal,
      );

      const mensagemAssistente: MensagemChat = {
        role: 'assistant',
        content: resposta.reply,
      };
      setMessages([...proximoHistorico, mensagemAssistente].slice(0, MAX_CHAT_MESSAGES));
      setDone(resposta.done);
      if (resposta.done && resposta.itinerary) {
        setItinerary(resposta.itinerary);
      }
    } catch (err: unknown) {
      if (controller.signal.aborted) {
        return;
      }
      // Reverte a mensagem não processada para não consumir o limite de 12 mensagens e restaura o texto no campo.
      setMessages(historicoAnterior);
      setInputText(conteudo);
      const traceId = extrairTraceIdDeExcecao(err);
      const mensagemAmigavel =
        err instanceof ChatApiError && err.message.trim() ? err.message : MENSAGEM_ERRO_PADRAO_CHAT;
      setErro({
        mensagem: mensagemAmigavel,
        traceId,
      });
    } finally {
      setIsSending(false);
    }
  }

  function handleFormSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void submeterMensagem(inputText);
  }

  function handleInputKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      if (!envioDesabilitado) {
        void submeterMensagem(inputText);
      }
    }
  }

  function handleTentarNovamente() {
    setErro(null);
    setCopiado(false);
    inputRef.current?.focus();
  }

  function handleNovaConversa() {
    abortControllerRef.current?.abort();
    setMessages([]);
    setInputText('');
    setDone(false);
    setItinerary(null);
    setErro(null);
    setMostrarModalEnvio(false);
    setCopiado(false);
    inputRef.current?.focus();
  }

  async function handleCopiarTraceId(traceId: string) {
    try {
      await navigator.clipboard?.writeText(traceId);
      setCopiado(true);
    } catch {
      setCopiado(false);
    }
  }

  return (
    <section className="card chat-ia-card" aria-label="Assistente de Roteiro com IA">
      <header className="chat-ia-header">
        <div>
          <h2 className="chat-ia-title">💬 Conversar com a IA para montar o roteiro</h2>
          <p className="chat-ia-subtitle">
            Personalize seu roteiro informando ritmo, acompanhantes e preferências gastronômicas.
          </p>
        </div>
        {(done || limiteMensagensAtingido) && (
          <button type="button" className="chat-ia-btn-secondary" onClick={handleNovaConversa}>
            Nova conversa
          </button>
        )}
      </header>

      <div className="chat-ia-context-row">
        <div className="chat-ia-field">
          <label htmlFor={inputOrigemId} className="chat-ia-label">
            Origem do roteiro no chat
          </label>
          <input
            id={inputOrigemId}
            type="text"
            className="chat-ia-input"
            value={origin}
            maxLength={MAX_CHAT_LOCATION_LENGTH}
            onChange={(e) => {
              setOrigemEditadaManual(true);
              setOrigin(e.target.value);
            }}
            disabled={isSending}
          />
        </div>
        <div className="chat-ia-field">
          <label htmlFor={inputDestinoId} className="chat-ia-label">
            Destino do roteiro no chat
          </label>
          <input
            id={inputDestinoId}
            type="text"
            className="chat-ia-input"
            value={destination}
            maxLength={MAX_CHAT_LOCATION_LENGTH}
            onChange={(e) => {
              setDestinoEditadoManual(true);
              setDestination(e.target.value);
            }}
            disabled={isSending}
          />
        </div>
      </div>

      <div
        className="chat-ia-log"
        role="log"
        aria-live="polite"
        aria-relevant="additions text"
        aria-busy={isSending}
        aria-label="Histórico da conversa com a IA"
      >
        {messages.length === 0 ? (
          <p className="chat-ia-empty">
            Envie uma mensagem para iniciar o diálogo guiado (ritmo, acompanhantes e gastronomia).
          </p>
        ) : (
          <ul className="chat-ia-message-list">
            {messages.map((msg, index) => (
              <li
                key={`${msg.role}-${index}`}
                className={`chat-ia-message chat-ia-message-${msg.role}`}
              >
                <span className="chat-ia-message-author">
                  {msg.role === 'user' ? 'Você' : 'Assistente IA'}
                </span>
                <p className="chat-ia-message-content">{msg.content}</p>
              </li>
            ))}
          </ul>
        )}

        {isSending && (
          <div className="chat-ia-typing" role="status">
            <span className="spinner-inline" aria-hidden="true" />
            <span>Assistente está digitando...</span>
          </div>
        )}
      </div>

      {erro && (
        <div className="chat-ia-error-wrapper">
          <ErroAmigavelJSX
            traceId={erro.traceId}
            mensagem={erro.mensagem}
            onTentarNovamente={handleTentarNovamente}
          />
          {!erroAmigavelImplementado && (
            <div className="chat-ia-error" role="alert">
              <p className="chat-ia-error-text">{erro.mensagem}</p>
              {erro.traceId && (
                <p className="chat-ia-error-trace">
                  Se o problema continuar, informe o código:{' '}
                  <code className="chat-ia-trace-code">{erro.traceId}</code>
                  <button
                    type="button"
                    className="chat-ia-btn-secondary chat-ia-copy-btn"
                    onClick={() => void handleCopiarTraceId(erro.traceId!)}
                  >
                    {copiado ? 'Código copiado' : 'Copiar código'}
                  </button>
                </p>
              )}
              <button
                type="button"
                className="chat-ia-btn-secondary"
                onClick={handleTentarNovamente}
              >
                Tentar novamente
              </button>
            </div>
          )}
        </div>
      )}

      <form className="chat-ia-form" onSubmit={handleFormSubmit} noValidate>
        <div className="chat-ia-input-group">
          <label htmlFor={inputMensagemId} className="chat-ia-label">
            Mensagem para o assistente
          </label>
          <div className="chat-ia-input-row">
            <input
              ref={inputRef}
              id={inputMensagemId}
              type="text"
              className="chat-ia-input chat-ia-message-input"
              placeholder="Ex.: Quero um roteiro com ritmo tranquilo..."
              value={inputText}
              aria-describedby={statusLimiteId}
              aria-invalid={limiteCaracteresExcedido}
              disabled={isSending || limiteMensagensAtingido}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={handleInputKeyDown}
            />
            <button type="submit" className="chat-ia-submit-btn" disabled={envioDesabilitado}>
              {isSending ? 'Enviando...' : 'Enviar'}
            </button>
          </div>
          <div id={statusLimiteId} className="chat-ia-counters" aria-live="polite">
            <span>
              {inputText.length}/{MAX_CHAT_MESSAGE_LENGTH} caracteres
            </span>
            <span>
              {messages.length}/{MAX_CHAT_MESSAGES} mensagens
            </span>
            {limiteCaracteresExcedido && (
              <span className="chat-ia-limit-warning" role="alert">
                Limite máximo de {MAX_CHAT_MESSAGE_LENGTH} caracteres por mensagem excedido.
              </span>
            )}
            {limiteMensagensAtingido && (
              <span className="chat-ia-limit-warning" role="status">
                Limite de {MAX_CHAT_MESSAGES} mensagens por conversa atingido.
              </span>
            )}
          </div>
        </div>
      </form>

      {done && itinerary && (
        <section className="chat-ia-itinerary" aria-label={`Roteiro final: ${itinerary.title}`}>
          <header className="chat-ia-itinerary-header">
            <div>
              <h3 className="chat-ia-itinerary-title">{itinerary.title}</h3>
              <p className="chat-ia-itinerary-route">
                {itinerary.origin} → {itinerary.destination}
                {typeof itinerary.distance_km === 'number' ? ` · ${itinerary.distance_km} km` : ''}
                {typeof itinerary.duration_min === 'number'
                  ? ` · ${itinerary.duration_min} min`
                  : ''}
              </p>
            </div>
            <div className="chat-ia-itinerary-actions">
              {isUrlHttpSegura(itinerary.map_url) && (
                <a
                  href={itinerary.map_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="chat-ia-btn-secondary chat-ia-map-link"
                >
                  Ver rota no Google Maps
                </a>
              )}
              <button
                type="button"
                className="chat-ia-send-itinerary-btn"
                disabled={!envioRoteiroDisponivel}
                title={envioRoteiroDisponivel ? 'Enviar roteiro' : 'Em breve'}
                onClick={() => {
                  if (envioRoteiroDisponivel) {
                    setMostrarModalEnvio(true);
                  }
                }}
              >
                Enviar por e-mail / WhatsApp
              </button>
            </div>
          </header>

          {itinerary.summary && <p className="chat-ia-itinerary-summary">{itinerary.summary}</p>}

          <div className="chat-ia-days-list">
            {itinerary.days.map((day) => (
              <article key={day.day} className="chat-ia-day-card">
                <h4 className="chat-ia-day-title">Dia {day.day}</h4>
                <ul className="chat-ia-activities-list">
                  {day.activities.map((activity, idx) => (
                    <li key={`${day.day}-${idx}`} className="chat-ia-activity-item">
                      <div className="chat-ia-activity-header">
                        {activity.time && (
                          <span className="chat-ia-activity-time">{activity.time}</span>
                        )}
                        <strong className="chat-ia-activity-title">{activity.title}</strong>
                      </div>
                      {activity.description && (
                        <p className="chat-ia-activity-desc">{activity.description}</p>
                      )}
                    </li>
                  ))}
                </ul>
              </article>
            ))}
          </div>

          {mostrarModalEnvio && envioRoteiroDisponivel && (
            <div className="chat-ia-dispatch-container">
              <EnvioRoteiroJSX itinerary={itinerary} onSent={() => setMostrarModalEnvio(false)} />
            </div>
          )}
        </section>
      )}
    </section>
  );
}
