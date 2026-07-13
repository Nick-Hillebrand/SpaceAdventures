import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiDelete, apiGet, apiPost, setAccessToken, type ApiError } from "@/lib/api";
import type { UserResponse } from "@/types/api";

export function useMe() {
  return useQuery<UserResponse, ApiError>({
    queryKey: ["auth", "me"],
    queryFn: () => apiGet<UserResponse>("/api/v1/auth/me"),
    retry: false,
  });
}

export function useSetConsent() {
  const qc = useQueryClient();
  return useMutation<UserResponse, ApiError, boolean>({
    mutationFn: (granted: boolean) =>
      apiPost<UserResponse>("/api/v1/auth/consent", { granted }),
    onSuccess: (user) => qc.setQueryData(["auth", "me"], user),
  });
}

export function useDeleteAccount() {
  const qc = useQueryClient();
  return useMutation<void, ApiError, string>({
    mutationFn: (password: string) => apiDelete<void>("/api/v1/auth/me", { password }),
    onSuccess: () => {
      setAccessToken(null);
      qc.clear();
    },
  });
}

export function useExportAccount() {
  return useMutation<Record<string, unknown>, ApiError, void>({
    mutationFn: () => apiGet<Record<string, unknown>>("/api/v1/auth/me/export"),
  });
}
