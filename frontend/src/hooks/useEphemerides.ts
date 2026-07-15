import { useQueries, useQuery } from "@tanstack/react-query";
import { apiGet, type ApiError } from "@/lib/api";
import type { EphemeridesResponse } from "@/types/api";
import { EPHEMERIDES_FETCH_PAST_DAYS, TRACKED_SPACECRAFT } from "@/solar/spacecraft";

function fetchEphemerides(slug: string): Promise<EphemeridesResponse> {
  const to = new Date();
  const from = new Date(to.getTime() - EPHEMERIDES_FETCH_PAST_DAYS * 86_400_000);
  const params = new URLSearchParams({ from: from.toISOString(), to: to.toISOString() });
  return apiGet<EphemeridesResponse>(`/api/v1/ephemerides/${encodeURIComponent(slug)}?${params}`);
}

/**
 * Fetches the full cached ephemeris window for one tracked object, once per
 * session (staleTime 1h — Architecture/22-ephemeris-and-mission-replay.md
 * B3: "fetch once per session per object"). Explicitly requests
 * `EPHEMERIDES_FETCH_PAST_DAYS` back (the backend's `MAX_RANGE_DAYS` cap)
 * rather than relying on the router's own 30-day default, so the trail has
 * the full 90 days of history the spec calls for.
 */
export function useEphemerides(slug: string | undefined) {
  return useQuery<EphemeridesResponse, ApiError>({
    queryKey: ["ephemerides", slug],
    queryFn: () => fetchEphemerides(slug!),
    enabled: Boolean(slug),
    staleTime: 60 * 60 * 1000,
  });
}

/**
 * The same fetch as `useEphemerides`, run once per entry in the fixed
 * `TRACKED_SPACECRAFT` catalog (a compile-time-constant-length list, so
 * `useQueries` over it doesn't run afoul of the rules of hooks the way a
 * variable-length list would).
 */
export function useTrackedSpacecraftEphemerides() {
  const results = useQueries({
    queries: TRACKED_SPACECRAFT.map((entry) => ({
      queryKey: ["ephemerides", entry.slug],
      queryFn: () => fetchEphemerides(entry.slug),
      staleTime: 60 * 60 * 1000,
    })),
  });
  return TRACKED_SPACECRAFT.map((entry, i) => ({ ...entry, query: results[i] }));
}
