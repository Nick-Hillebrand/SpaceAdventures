import { useQuery } from "@tanstack/react-query";
import { apiGet, type ApiError } from "@/lib/api";
import type { NeoFeedResponse } from "@/types/api";

export function useNeoFeed(start: string, end: string) {
  return useQuery<NeoFeedResponse, ApiError>({
    queryKey: ["neo", "feed", start, end],
    queryFn: () => {
      const params = new URLSearchParams({ start, end });
      return apiGet<NeoFeedResponse>(`/api/v1/neo/feed?${params.toString()}`);
    },
    enabled: Boolean(start) && Boolean(end),
  });
}
