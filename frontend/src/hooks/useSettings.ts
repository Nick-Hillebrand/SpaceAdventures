import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost, type ApiError } from "@/lib/api";
import type { SettingsStatus } from "@/types/api";

export function useSettings() {
  return useQuery<SettingsStatus, ApiError>({
    queryKey: ["settings"],
    queryFn: () => apiGet<SettingsStatus>("/api/v1/settings"),
  });
}

export function useSetNasaApiKey() {
  const qc = useQueryClient();
  return useMutation<{ message: string }, ApiError, { api_key: string }>({
    mutationFn: (body) => apiPost("/api/v1/settings/nasa-api-key", body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["settings"] }); },
  });
}

export function useSetN2yoApiKey() {
  const qc = useQueryClient();
  return useMutation<{ message: string }, ApiError, { api_key: string }>({
    mutationFn: (body) => apiPost("/api/v1/settings/n2yo-api-key", body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["settings"] }); },
  });
}
