import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { apiGet, type ApiError } from "@/lib/api";
import type { LaunchesResponse } from "@/types/api";

export function useLaunches() {
  const { i18n } = useTranslation();
  const lang = i18n.resolvedLanguage ?? "en";
  return useQuery<LaunchesResponse, ApiError>({
    queryKey: ["launches", "upcoming", lang],
    queryFn: () => apiGet<LaunchesResponse>(`/api/v1/launches/upcoming?lang=${encodeURIComponent(lang)}`),
    staleTime: 300_000, // 5 minutes per spec
  });
}
