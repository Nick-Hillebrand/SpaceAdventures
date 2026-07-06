import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiDelete, apiGet, apiPost, type ApiError } from "@/lib/api";
import type {
  CreateSubscriptionRequest,
  SubscriptionData,
  SubscriptionsResponse,
} from "@/types/api";

export function useSubscriptions() {
  return useQuery<SubscriptionsResponse, ApiError>({
    queryKey: ["subscriptions"],
    queryFn: () => apiGet<SubscriptionsResponse>("/api/v1/subscriptions"),
    retry: false,
  });
}

export function useCreateSubscription() {
  const qc = useQueryClient();
  return useMutation<SubscriptionData, ApiError, CreateSubscriptionRequest>({
    mutationFn: (data: CreateSubscriptionRequest) =>
      apiPost<SubscriptionData>("/api/v1/subscriptions", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["subscriptions"] }),
  });
}

export function useDeleteSubscription() {
  const qc = useQueryClient();
  return useMutation<void, ApiError, string>({
    mutationFn: (id: string) => apiDelete<void>(`/api/v1/subscriptions/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["subscriptions"] }),
  });
}
