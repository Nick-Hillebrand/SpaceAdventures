import { useQuery } from "@tanstack/react-query";
import { apiGet, type ApiError } from "@/lib/api";
import type { UserResponse } from "@/types/api";

export function useMe() {
  return useQuery<UserResponse, ApiError>({
    queryKey: ["auth", "me"],
    queryFn: () => apiGet<UserResponse>("/api/v1/auth/me"),
    retry: false,
  });
}
