import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, json } from './client';

export type IntegrationKind = 'sonarr' | 'radarr' | 'tmdb' | 'plex';

export interface PathMapping {
  remote: string;
  local: string;
}

export interface Integration {
  id: number;
  kind: IntegrationKind;
  name: string;
  base_url: string;
  verify_tls: boolean;
  path_mappings: PathMapping[];
  enabled: boolean;
  api_key_hint: string;
  last_notify?: { at: string; ok: boolean; message: string } | null;
}

export interface IntegrationForm {
  kind: IntegrationKind;
  name: string;
  base_url: string;
  api_key: string;
  verify_tls: boolean;
  path_mappings: PathMapping[];
  enabled: boolean;
}

export interface TestResult {
  ok: boolean;
  app: string | null;
  version: string | null;
  error_code: string | null;
  message: string | null;
}

export const KIND_LABELS: Record<IntegrationKind, string> = {
  sonarr: 'Sonarr',
  radarr: 'Radarr',
  tmdb: 'TMDB',
  plex: 'Plex',
};

const KEY = ['integrations'] as const;

export function useIntegrations() {
  return useQuery({ queryKey: KEY, queryFn: () => api<Integration[]>('integrations') });
}

function useSave<TBody, TResult>(request: (body: TBody) => Promise<TResult>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: request,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
  });
}

export const useCreateIntegration = () =>
  useSave((body: IntegrationForm) =>
    api<Integration>('integrations', { method: 'POST', body: json(body) }),
  );

export const useUpdateIntegration = () =>
  useSave(({ id, api_key, kind: _kind, ...rest }: IntegrationForm & { id: number }) =>
    api<Integration>(`integrations/${id}`, {
      method: 'PATCH',
      // An empty key field means "keep the saved key".
      body: json(api_key ? { ...rest, api_key } : rest),
    }),
  );

export const useDeleteIntegration = () =>
  useSave((id: number) => api(`integrations/${id}`, { method: 'DELETE' }));

export function useTestIntegration() {
  return useMutation({
    mutationFn: (body: {
      kind: IntegrationKind;
      base_url: string;
      api_key?: string;
      verify_tls: boolean;
      id?: number;
    }) => api<TestResult>('integrations/test', { method: 'POST', body: json(body) }),
  });
}
