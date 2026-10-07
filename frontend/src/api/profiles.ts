import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, json } from './client';

export interface ProfileSettings {
  codec: 'hevc' | 'av1' | 'h264';
  quality: number;
  speed: 'fast' | 'balanced' | 'slow';
  ten_bit: boolean;
  max_height: 2160 | 1440 | 1080 | 720 | null;
  audio: 'copy' | 'compress_lossless' | 'convert';
  audio_codec: AudioCodec;
  audio_kbps_per_channel: number | null;
  add_stereo_aac: boolean;
  min_savings_percent: number;
}

export interface Profile {
  id: number;
  name: string;
  builtin: boolean;
  settings: ProfileSettings;
  source: string;
  mimic: MimicSaved | null;
  used_by: string[];
  updated_at: string;
}

export const CODEC_LABELS = { hevc: 'HEVC (H.265)', av1: 'AV1', h264: 'H.264' } as const;

export type AudioCodec = 'eac3' | 'aac' | 'opus';
export const AUDIO_CODEC_LABELS: Record<AudioCodec, string> = {
  eac3: 'E-AC-3',
  aac: 'AAC',
  opus: 'Opus',
};
// Same defaults and limits as the backend (audio_rules.py).
export const DEFAULT_KBPS_PER_CHANNEL: Record<AudioCodec, number> = {
  eac3: 112,
  aac: 64,
  opus: 48,
};
const MAX_TRACK_KBPS: Record<AudioCodec, number> = { eac3: 640, aac: 512, opus: 510 };

export function trackKbps(s: ProfileSettings, channels: number): number {
  const per = s.audio_kbps_per_channel ?? DEFAULT_KBPS_PER_CHANNEL[s.audio_codec];
  return Math.min(per * channels, MAX_TRACK_KBPS[s.audio_codec]);
}

function describeAudio(s: ProfileSettings): string {
  if (s.audio === 'copy') return 'audio copied';
  const target = `${AUDIO_CODEC_LABELS[s.audio_codec]} ${trackKbps(s, 6)}k for 5.1`;
  return s.audio === 'compress_lossless' ? `lossless audio to ${target}` : `audio to ${target}`;
}

export function describe(s: ProfileSettings): string {
  return [
    CODEC_LABELS[s.codec],
    s.ten_bit ? '10-bit' : '8-bit',
    `quality ${s.quality}/10`,
    s.max_height ? `max ${s.max_height}p` : 'keep resolution',
    describeAudio(s),
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
  useProfileMutation(
    ({
      id,
      ...body
    }: {
      id?: number;
      name: string;
      settings: ProfileSettings;
      mimic?: MimicSaved | null;
    }) =>
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

// --- mimic (ARCHITECTURE.md §7.2) -----------------------------------------------------------

export type FieldSource = 'read' | 'estimated' | 'default';

export interface MimicSaved {
  file: string;
  sources: Record<string, FieldSource>;
  notes: string[];
}

export interface MimicReport {
  settings: ProfileSettings;
  sources: Record<string, FieldSource>;
  notes: string[];
  sample: Record<string, string | number | null>;
}

export function useMimic(fileId: number | null) {
  return useQuery({
    queryKey: ['mimic', fileId],
    queryFn: () => api<{ file: string; report: MimicReport }>(`files/${fileId}/mimic`),
    enabled: fileId !== null,
    staleTime: Infinity,
  });
}
