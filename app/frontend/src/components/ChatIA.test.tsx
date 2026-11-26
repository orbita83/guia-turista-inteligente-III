import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vite-plus/test';

import { ApiError } from '../services/api';
import { ChatApiError, enviarMensagem } from '../services/chatApi';
import type { Itinerary } from '../types/chat';
import { ChatIA } from './ChatIA';

const ROTEIRO_EXEMPLO: Itinerary = {
  trip_id: 'trip-exemplo-001',
  title: 'Roteiro Teresina a Piripiri',
  origin: 'Teresina - PI',
  destination: 'Piripiri - PI',
  distance_km: 165.4,
  duration_min: 140,
  summary: 'Viagem cultural e de ecoturismo pelo norte do Piauí.',
  days: [
    {
      day: 1,
      activities: [
        {
          time: '09:00',
          title: 'Parque Nacional de Sete Cidades',
          description: 'Trilha guiada pelas formações rochosas e pinturas rupestres.',
        },
        {
          time: '15:00',
          title: 'Cachoeira do Urubu',
          description: 'Parada contemplativa no fim da tarde.',
        },
      ],
    },
  ],
  map_url: 'https://www.google.com/maps/dir/?api=1&origin=Teresina-PI&destination=Piripiri-PI',
};

describe('ChatIA e chatApi (Issue #12 · T0016)', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('conclui um roteiro só pela conversa usando Enter, devolve o foco ao campo e exibe o roteiro final', async () => {
    const user = userEvent.setup();
    const respostas = [
      {
        reply: 'Qual ritmo você prefere para a viagem: tranquilo, moderado ou intenso?',
        done: false,
        itinerary: null,
      },
      {
        reply: 'Com quem você vai viajar: sozinho, casal, família com crianças ou amigos?',
        done: false,
        itinerary: null,
      },
      {
        reply: 'Aqui está seu roteiro personalizado para Piripiri!',
        done: true,
        itinerary: ROTEIRO_EXEMPLO,
      },
    ];
    let chamada = 0;

    const fetchMock = vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const respostaAtual = respostas[chamada] ?? respostas[respostas.length - 1];
      chamada += 1;
      expect(init?.method).toBe('POST');
      return Response.json(respostaAtual, { status: 200 });
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<ChatIA />);

    const log = screen.getByRole('log', { name: /Histórico da conversa com a IA/i });
    expect(log).toHaveAttribute('aria-live', 'polite');

    const campoMensagem = screen.getByLabelText('Mensagem para o assistente');
    const botaoEnviar = screen.getByRole('button', { name: 'Enviar' });
    expect(botaoEnviar).toBeDisabled();

    // 1ª troca enviada com Enter
    await user.type(campoMensagem, 'Quero um roteiro com ritmo tranquilo{Enter}');
    expect(await screen.findByText(/Qual ritmo você prefere/i)).toBeInTheDocument();
    await waitFor(() => expect(campoMensagem).toHaveFocus());

    // 2ª troca enviada com Enter
    await user.type(campoMensagem, 'Vamos viajar em casal{Enter}');
    expect(await screen.findByText(/Com quem você vai viajar/i)).toBeInTheDocument();
    await waitFor(() => expect(campoMensagem).toHaveFocus());

    // 3ª troca enviada com clique no botão Enviar -> conclui roteiro
    await user.type(campoMensagem, 'Gostamos de culinária regional como Maria Isabel');
    expect(botaoEnviar).toBeEnabled();
    await user.click(botaoEnviar);

    expect(
      await screen.findByRole('heading', { name: 'Roteiro Teresina a Piripiri' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Dia 1')).toBeInTheDocument();
    expect(screen.getByText('Parque Nacional de Sete Cidades')).toBeInTheDocument();
    expect(screen.getByText('Cachoeira do Urubu')).toBeInTheDocument();

    const botaoEnvio = screen.getByRole('button', { name: 'Enviar por e-mail / WhatsApp' });
    expect(botaoEnvio).toBeDisabled();
    expect(botaoEnvio).toHaveAttribute('title', 'Em breve');
  });

  it('exibe estado digitando durante o envio e desabilita o botão', async () => {
    const user = userEvent.setup();
    let resolverRequisicao: ((resp: Response) => void) | undefined;

    vi.stubGlobal(
      'fetch',
      vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            resolverRequisicao = resolve;
          }),
      ),
    );

    render(<ChatIA />);
    const campoMensagem = screen.getByLabelText('Mensagem para o assistente');
    await user.type(campoMensagem, 'Olá assistente');
    await user.click(screen.getByRole('button', { name: 'Enviar' }));

    expect(screen.getByText('Assistente está digitando...')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Enviando...' })).toBeDisabled();

    resolverRequisicao?.(
      Response.json({
        reply: 'Olá! Qual ritmo você prefere?',
        done: false,
        itinerary: null,
      }),
    );

    expect(await screen.findByText('Olá! Qual ritmo você prefere?')).toBeInTheDocument();
    expect(screen.queryByText('Assistente está digitando...')).not.toBeInTheDocument();
  });

  it('mostra erro amigável com trace_id e sem dados técnicos (stack/latência) quando o backend falha', async () => {
    const user = userEvent.setup();

    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        Response.json(
          {
            detail: 'Traceback (most recent call last): RuntimeError em guide.py latency=420ms',
            trace_id: 'trace-uuid-987654',
          },
          {
            status: 500,
            headers: { 'X-Request-ID': 'header-req-id-123' },
          },
        ),
      ),
    );

    render(<ChatIA />);
    const campoMensagem = screen.getByLabelText('Mensagem para o assistente');
    await user.type(campoMensagem, 'Teste de falha{Enter}');

    const alerta = await screen.findByRole('alert');
    expect(alerta).toHaveTextContent(/Algo deu errado ao conversar com o assistente/i);
    expect(alerta).toHaveTextContent('trace-uuid-987654');
    expect(alerta).not.toHaveTextContent(/Traceback/i);
    expect(alerta).not.toHaveTextContent(/RuntimeError/i);
    expect(alerta).not.toHaveTextContent(/420ms/i);

    await user.click(screen.getByRole('button', { name: 'Tentar novamente' }));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(campoMensagem).toHaveFocus();
  });

  it('extrai trace_id do cabeçalho X-Request-ID em ChatApiError quando o corpo não traz trace_id', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(JSON.stringify({ detail: 'Falha interna' }), {
            status: 502,
            headers: {
              'Content-Type': 'application/json',
              'X-Request-ID': 'req-header-abc-999',
            },
          }),
      ),
    );

    let capturado: unknown;
    try {
      await enviarMensagem([{ role: 'user', content: 'Oi' }], 'Teresina - PI', 'Piripiri - PI');
    } catch (err) {
      capturado = err;
    }

    expect(capturado).toBeInstanceOf(ApiError);
    expect(capturado).toBeInstanceOf(ChatApiError);
    expect((capturado as ChatApiError).trace_id).toBe('req-header-abc-999');
    expect((capturado as ChatApiError).status).toBe(502);
  });

  it('respeita os limites de 1000 caracteres por mensagem e 12 mensagens na conversa', async () => {
    const user = userEvent.setup();
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        Response.json({
          reply: 'Continue informando os detalhes.',
          done: false,
          itinerary: null,
        }),
      ),
    );

    render(<ChatIA />);
    const campoMensagem = screen.getByLabelText('Mensagem para o assistente');
    const botaoEnviar = screen.getByRole('button', { name: 'Enviar' });

    // Acima de 1000 caracteres -> desabilita envio e exibe alerta de limite
    fireEvent.change(campoMensagem, { target: { value: 'a'.repeat(1001) } });
    expect(botaoEnviar).toBeDisabled();
    expect(
      screen.getByText(/Limite máximo de 1000 caracteres por mensagem excedido/i),
    ).toBeInTheDocument();

    // 6 trocas completas (6 user + 6 assistant = 12 mensagens) -> atinge limite de 12 mensagens
    for (let i = 1; i <= 6; i += 1) {
      fireEvent.change(campoMensagem, { target: { value: `Mensagem ${i}` } });
      await user.click(botaoEnviar);
      await waitFor(() => expect(screen.getByText(`${i * 2}/12 mensagens`)).toBeInTheDocument());
    }

    expect(screen.getByText(/Limite de 12 mensagens por conversa atingido/i)).toBeInTheDocument();
    expect(campoMensagem).toBeDisabled();
    expect(botaoEnviar).toBeDisabled();
  });
});
