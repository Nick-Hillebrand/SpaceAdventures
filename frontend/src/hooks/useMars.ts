import { useQuery } from "@tanstack/react-query";
import { apiGet, type ApiError } from "@/lib/api";
import type { MarsPhotosResponse, RoversResponse } from "@/types/api";

export function useRovers() {
  return useQuery<RoversResponse, ApiError>({
    queryKey: ["mars", "rovers"],
    queryFn: () => apiGet<RoversResponse>("/api/v1/mars/rovers"),
  });
}

export interface MarsPhotosParams {
  rover: string;
  sol?: number | null;
  earthDate?: string | null;
  camera?: string | null;
  page?: number;
}

export function useMarsPhotos({ rover, sol, earthDate, camera, page = 1 }: MarsPhotosParams) {
  const enabled = Boolean(rover) && (sol != null || Boolean(earthDate));
  return useQuery<MarsPhotosResponse, ApiError>({
    queryKey: ["mars", "photos", rover, sol, earthDate, camera, page],
    queryFn: () => {
      const params = new URLSearchParams({ rover, page: String(page) });
      if (sol != null) params.set("sol", String(sol));
      if (earthDate) params.set("earth_date", earthDate);
      if (camera) params.set("camera", camera);
      return apiGet<MarsPhotosResponse>(`/api/v1/mars/photos?${params.toString()}`);
    },
    enabled,
  });
}
