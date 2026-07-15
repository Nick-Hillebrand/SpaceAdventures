import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiDelete, apiGet, apiPost, type ApiError } from "@/lib/api";
import type { LocationOut, LocationSearchResponse, SetLocationRequest } from "@/types/api";

export function useSearchLocation() {
  return useMutation<LocationSearchResponse, ApiError, string>({
    mutationFn: (q: string) =>
      apiGet<LocationSearchResponse>(`/api/v1/location/search?q=${encodeURIComponent(q)}`),
  });
}

export function useSetLocation() {
  const qc = useQueryClient();
  return useMutation<LocationOut, ApiError, SetLocationRequest>({
    mutationFn: (data: SetLocationRequest) => apiPost<LocationOut>("/api/v1/location", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["auth", "me"] }),
  });
}

export function useClearLocation() {
  const qc = useQueryClient();
  return useMutation<void, ApiError, void>({
    mutationFn: () => apiDelete<void>("/api/v1/location"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["auth", "me"] }),
  });
}
