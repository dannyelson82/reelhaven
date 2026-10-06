import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, json } from './client';

export interface LanguagePolicy {
  keep_languages: string[];
  keep_original: boolean;
  keep_subtitles_full: boolean;
  keep_subtitles_forced: boolean;
  keep_subtitles_sdh: boolean;
  keep_commentary: boolean;
  untagged: string;
  set_defaults: boolean;
  wrong_language_action: 'flag';
}

export interface TrackPlan {
  index: number;
  kind: 'audio' | 'subtitle';
  language: string | null;
  title: string | null;
  keep: boolean;
  default_before: boolean;
  default_after: boolean;
  reason: string;
}

export interface Plan {
  action: 'skip' | 'remux';
  tracks: TrackPlan[];
  flags: string[];
  summary: string;
  details: string[];
  removed_bytes: number | null;
}

export const FLAG_LABELS: Record<string, string> = {
  wrong_language: 'Wrong language',
  no_wanted_audio: 'No wanted audio',
  dolby_vision: 'Dolby Vision',
  no_audio: 'No audio',
  probe_failed: "Can't read",
};

export function usePolicy(libraryId: number) {
  return useQuery({
    queryKey: ['policy', libraryId],
    queryFn: () => api<LanguagePolicy>(`libraries/${libraryId}/policy`),
  });
}

export function useSavePolicy(libraryId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (policy: LanguagePolicy) =>
      api<LanguagePolicy>(`libraries/${libraryId}/policy`, { method: 'PUT', body: json(policy) }),
    onSuccess: (saved) => {
      queryClient.setQueryData(['policy', libraryId], saved);
      void queryClient.invalidateQueries({ queryKey: ['plan'] });
      void queryClient.invalidateQueries({ queryKey: ['dry-run', libraryId] });
    },
  });
}

export function usePlan(fileId: number | null) {
  return useQuery({
    queryKey: ['plan', fileId],
    queryFn: () => api<Plan>(`files/${fileId}/plan`),
    enabled: fileId !== null,
    retry: false,
  });
}
