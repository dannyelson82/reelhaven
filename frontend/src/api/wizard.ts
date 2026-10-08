import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, json } from './client';
import type { ProfileSettings } from './profiles';

export interface EstimateSummary {
  files: number;
  encode: number;
  remux: number;
  saved_bytes: number;
  savings_unknown: number;
}

/** A scan still reading the library: estimates cover the files read so far (ADR-0027). */
export interface Reading {
  probed: number;
  to_probe: number;
  found_bytes: number;
}

export interface Estimate {
  library_bytes: number;
  results: Record<string, EstimateSummary>;
  reading: Reading | null;
}

/** What each candidate profile would save on a library (read-only, ADR-0026). */
export function useEstimate(libraryId: number, candidates: Record<string, ProfileSettings | null>) {
  const body = JSON.stringify({ profiles: candidates });
  return useQuery({
    queryKey: ['estimate', libraryId, body],
    queryFn: () => api<Estimate>(`libraries/${libraryId}/estimate`, { method: 'POST', body }),
    enabled: Object.keys(candidates).length > 0,
    staleTime: 60_000,
    // While the library is still being read, the estimate improves: refresh it.
    refetchInterval: (query) => (query.state.data?.reading ? 15_000 : false),
  });
}

export interface Onboarding {
  wizard_seen: boolean;
  server_steps_done: boolean;
}

export function useOnboarding() {
  return useQuery({ queryKey: ['onboarding'], queryFn: () => api<Onboarding>('onboarding') });
}

export function useSaveOnboarding() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (value: Onboarding) =>
      api<Onboarding>('onboarding', { method: 'PUT', body: json(value) }),
    onSuccess: (saved) => queryClient.setQueryData(['onboarding'], saved),
  });
}
