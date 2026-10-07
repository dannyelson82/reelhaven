import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, json } from './client';

export interface ProfileSettings {
  codec: 'hevc' | 'av1' | 'h264';
  quality: number;
  speed: 'fast' | 'balanced' | 'slow';
  ten_bit: boolean;
  max_height: 2160 | 1440 | 1080 | 720 | null;
  audio: 'copy' | 'compress_lossless';
  add_stereo_aac: boolean;
  min_savings_percent: number;
}

export interface Profile {
  id: number;
  name: string;
  builtin: boolean;
  settings: ProfileSettings;
  source: string;
  used_by: string[];
  updated_at: string;
}

export const CODEC_LABELS = { hevc: 'HEVC (H.265)', av1: 'AV1', h264: 'H.264' } as const;

export function describe(s: ProfileSettings): string {
  return [
    CODEC_LABELS[s.codec],
    s.ten_bit ? '10-bit' : '8-bit',
    `quality ${s.quality}/10`,
    s.max_height ? `max ${s.max_height}p` : 'keep resolution',
    s.audio === 'copy' ? 'audio copied' : 'lossless audio compressed',
  ].join(' · ');
}

const KEY = ['profiles'] as const;

export function useProfiles() {
  return useQuery({ queryKey: KEY, queryFn: () => api<Profile[]>('profiles') });
}

function useProfileMutation<TBody, TResult>(request: (body: TBody) => Promise<TResult>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: request,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: KEY });
      void queryClient.invalidateQueries({ queryKey: ['library-profile'] });
    },
  });
}

export const useSaveProfile = () =>
  useProfileMutation(({ id, ...body }: { id?: number; name: string; settings: ProfileSettings }) =>
    api<Profile>(id ? `profiles/${id}` : 'profiles', {
      method: id ? 'PUT' : 'POST',
      body: json(body),
    }),
  );

export const useDeleteProfile = () =>
  useProfileMutation((id: number) => api(`profiles/${id}`, { method: 'DELETE' }));

export function useLibraryProfile(libraryId: number) {
  return useQuery({
    queryKey: ['library-profile', libraryId],
    queryFn: () => api<{ profile_id: number | null }>(`libraries/${libraryId}/profile`),
  });
}

export const useSetLibraryProfile = (libraryId: number) =>
  useProfileMutation((profileId: number | null) =>
    api(`libraries/${libraryId}/profile`, { method: 'PUT', body: json({ profile_id: profileId }) }),
  );
