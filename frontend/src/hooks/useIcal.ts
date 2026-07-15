import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiPost, type ApiError } from "@/lib/api";
import type { IcalRotateResponse } from "@/types/api";

export function useRotateIcalToken() {
  const qc = useQueryClient();
  return useMutation<IcalRotateResponse, ApiError, void>({
    mutationFn: () => apiPost<IcalRotateResponse>("/api/v1/ical/rotate", {}),
    onSuccess: (data) => {
      // Patch the cached /auth/me so the AccountPage's webcal:// URL updates
      // immediately without a round-trip.
      qc.setQueryData(["auth", "me"], (prev: Record<string, unknown> | undefined) => {
        if (!prev) return prev;
        return { ...prev, ical_token: data.ical_token };
      });
    },
  });
}
