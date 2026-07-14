import { useQuery } from "@tanstack/react-query";
import { apiGet, type ApiError } from "@/lib/api";
import type { LaunchHistoryResponse } from "@/types/api";

export function useLaunchHistory(ll2Id: string | undefined) {
  return useQuery<LaunchHistoryResponse, ApiError>({
    queryKey: ["launches", "history", ll2Id],
    queryFn: () => apiGet<LaunchHistoryResponse>(`/api/v1/launches/${encodeURIComponent(ll2Id!)}/history`),
    enabled: Boolean(ll2Id),
    staleTime: 300_000,
  });
}
