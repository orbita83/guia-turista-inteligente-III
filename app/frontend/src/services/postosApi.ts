import type { CoordenadaGPS } from '../types/domain';
import type { ResultadoPostosAnp } from '../types/postos';
import { request } from './api';

export function buscarPostosAoLongoDaRota(
  geometria: CoordenadaGPS[],
  signal: AbortSignal,
): Promise<ResultadoPostosAnp> {
  return request<ResultadoPostosAnp>('/postos/ao-longo-da-rota', {
    method: 'POST',
    body: JSON.stringify({ geometria }),
    signal,
  });
}
