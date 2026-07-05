export interface ApodData {
  date: string;
  title: string;
  explanation: string;
  url: string;
  hdurl?: string | null;
  media_type: string;
  copyright?: string | null;
  thumbnail_url?: string | null;
}

export interface ApodResponse {
  data: ApodData;
  cached: boolean;
  stale: boolean;
  fetched_at: string;
  is_today: boolean;
}
