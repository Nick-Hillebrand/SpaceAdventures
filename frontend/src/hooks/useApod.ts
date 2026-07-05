import { useQuery } from "@tanstack/react-query";
import { apiGet, type ApiError } from "@/lib/api";
import type { ApodResponse } from "@/types/api";

export function useApod(date?: string) {
  return useQuery<ApodResponse, ApiError>({
    queryKey: ["apod", date ?? "today"],
    queryFn: () => {
      const search = date ? `?date=${encodeURIComponent(date)}` : "";
      return apiGet<ApodResponse>(`/api/v1/apod${search}`);
    },
  });
}
