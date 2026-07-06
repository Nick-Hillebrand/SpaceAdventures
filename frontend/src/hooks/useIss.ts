import { useQuery } from "@tanstack/react-query";
import { apiGet, type ApiError } from "@/lib/api";
import type {
  IssPassesResponse,
  IssPositionsResponse,
  IssQuotaResponse,
  IssTleResponse,
} from "@/types/api";

export function useIssPositions() {
  return useQuery<IssPositionsResponse, ApiError>({
    queryKey: ["iss", "positions"],
    queryFn: () => apiGet<IssPositionsResponse>("/api/v1/iss/positions"),
    staleTime: 270_000, // 270 s — triggers refetch 30 s before 5-min batch expires
  });
}

export function useIssTle() {
  return useQuery<IssTleResponse, ApiError>({
    queryKey: ["iss", "tle"],
    queryFn: () => apiGet<IssTleResponse>("/api/v1/iss/tle"),
  });
}

export function useIssVisualPasses(lat: number, lng: number, alt: number) {
  return useQuery<IssPassesResponse, ApiError>({
    queryKey: ["iss", "passes", "visual", lat, lng, alt],
    queryFn: () =>
      apiGet<IssPassesResponse>(
        `/api/v1/iss/passes/visual?lat=${lat}&lng=${lng}&alt=${alt}`,
      ),
  });
}

export function useIssRadioPasses(lat: number, lng: number, alt: number) {
  return useQuery<IssPassesResponse, ApiError>({
    queryKey: ["iss", "passes", "radio", lat, lng, alt],
    queryFn: () =>
      apiGet<IssPassesResponse>(
        `/api/v1/iss/passes/radio?lat=${lat}&lng=${lng}&alt=${alt}`,
      ),
  });
}

export function useIssQuota() {
  return useQuery<IssQuotaResponse, ApiError>({
    queryKey: ["iss", "quota"],
    queryFn: () => apiGet<IssQuotaResponse>("/api/v1/iss/quota"),
  });
}
