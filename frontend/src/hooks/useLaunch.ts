import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { apiGet, type ApiError } from "@/lib/api";
import type { LaunchData } from "@/types/api";

export function useLaunch(ll2Id: string | undefined) {
  const { i18n } = useTranslation();
  const lang = i18n.resolvedLanguage ?? "en";
  return useQuery<LaunchData, ApiError>({
    queryKey: ["launches", "detail", ll2Id, lang],
    queryFn: () =>
      apiGet<LaunchData>(`/api/v1/launches/${encodeURIComponent(ll2Id!)}?lang=${encodeURIComponent(lang)}`),
    enabled: Boolean(ll2Id),
    staleTime: 300_000,
  });
}
