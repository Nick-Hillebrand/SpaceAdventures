import { useQuery } from "@tanstack/react-query";
import { apiGet, type ApiError } from "@/lib/api";
import type { SpaceWeatherEventType, SpaceWeatherResponse } from "@/types/api";

const ROUTE_MAP: Record<SpaceWeatherEventType, string> = {
  FLR: "/api/v1/space-weather/flares",
  GST: "/api/v1/space-weather/storms",
  CME: "/api/v1/space-weather/cmes",
  SEP: "/api/v1/space-weather/sep",
  RBE: "/api/v1/space-weather/rbe",
};

export function useSpaceWeatherEvents(
  eventType: SpaceWeatherEventType,
  start: string,
  end: string,
) {
  return useQuery<SpaceWeatherResponse, ApiError>({
    queryKey: ["space-weather", eventType, start, end],
    queryFn: () => {
      const params = new URLSearchParams({ start, end });
      return apiGet<SpaceWeatherResponse>(`${ROUTE_MAP[eventType]}?${params.toString()}`);
    },
    enabled: Boolean(start) && Boolean(end),
  });
}
