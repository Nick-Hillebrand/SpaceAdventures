import { useQuery } from "@tanstack/react-query";
import { apiGet, type ApiError } from "@/lib/api";
import type { SettingsStatus } from "@/types/api";

// API keys are server configuration set via environment variables; the
// former mutation hooks targeted endpoints that allowed unauthenticated
// key overwrites and have been removed.

export function useSettings() {
  return useQuery<SettingsStatus, ApiError>({
    queryKey: ["settings"],
    queryFn: () => apiGet<SettingsStatus>("/api/v1/settings"),
  });
}
