import { useQuery } from "@tanstack/react-query";
import { apiGet, type ApiError } from "@/lib/api";
import type { LaunchesResponse } from "@/types/api";

export function useLaunches() {
  return useQuery<LaunchesResponse, ApiError>({
    queryKey: ["launches", "upcoming"],
    queryFn: () => apiGet<LaunchesResponse>("/api/v1/launches/upcoming"),
    staleTime: 300_000, // 5 minutes per spec
  });
}
