import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { apiGet, type ApiError } from "@/lib/api";
import type { ApodResponse } from "@/types/api";

export function useApod(date?: string) {
  const { i18n } = useTranslation();
  const lang = i18n.resolvedLanguage ?? "en";
  return useQuery<ApodResponse, ApiError>({
    queryKey: ["apod", date ?? "today", lang],
    queryFn: () => {
      const params = new URLSearchParams({ lang });
      if (date) params.set("date", date);
      return apiGet<ApodResponse>(`/api/v1/apod?${params.toString()}`);
    },
  });
}
