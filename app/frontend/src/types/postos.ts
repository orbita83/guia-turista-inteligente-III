export interface PostoAnp {
  cnpj: string;
  legal_name: string;
  rating: number | null;
  authorized_since: string;
  authorization_years: number;
  fuels: string[];
  latitude: number;
  longitude: number;
  distance_from_route_km: number;
  rank: number;
}

export interface ResultadoPostosAnp {
  postos: PostoAnp[];
  data_reference_date: string;
}
