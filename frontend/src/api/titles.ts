import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, json } from './client';

export interface LanguageOption {
  code: string;
  name: string;
  alpha2?: string | null;
}

export const SOURCE_LABELS: Record<string, string> = {
  sonarr: 'Sonarr',
  radarr: 'Radarr',
  tmdb: 'TMDB',
  manual: 'set by you',
  unknown: 'unknown',
};

export function useLanguages() {
  return useQuery({
    queryKey: ['languages'],
    queryFn: () => api<LanguageOption[]>('languages'),
    staleTime: Infinity,
  });
}

export function useSetTitleLanguage(libraryId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ titleId, language }: { titleId: number; language: string | null }) =>
      api(`titles/${titleId}/language`, { method: 'PUT', body: json({ language }) }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['files', libraryId] });
      void queryClient.invalidateQueries({ queryKey: ['file'] });
      void queryClient.invalidateQueries({ queryKey: ['plan'] });
      void queryClient.invalidateQueries({ queryKey: ['dry-run', libraryId] });
    },
  });
}

export function useRefreshLanguages(libraryId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api<{ started: boolean }>(`libraries/${libraryId}/languages/refresh`, { method: 'POST' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['scan', libraryId] }),
  });
}
