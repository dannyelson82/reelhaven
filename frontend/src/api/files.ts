import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';

export interface ScanStatus {
  state: 'scanning' | 'done' | 'error';
  phase: 'listing' | 'probing' | 'saving' | 'languages';
  found: number;
  to_probe: number;
  probed: number;
  failed: number;
  unchanged: number;
  moved: number;
  removed: number;
  unstable: number;
  languages_resolved: number;
  languages_unknown: number;
  language_errors: string[];
  error: string | null;
  started_at: number;
  finished_at: number | null;
}

export interface FileSummary {
  id: number;
  relative_path: string;
  size: number;
  status: 'ok' | 'probe_failed';
  duration_s: number | null;
  video_codec: string | null;
  width: number | null;
  height: number | null;
  hdr: string | null;
  audio_languages: (string | null)[];
  subtitle_languages: (string | null)[];
  probe_error: string | null;
  title_id: number | null;
  original_language: string | null;
  language_source: string | null;
}

export interface Stream {
  index: number;
  kind: 'video' | 'audio' | 'subtitle' | 'attachment' | 'data';
  codec: string | null;
  profile: string | null;
  language: string | null;
  raw_language: string | null;
  title: string | null;
  default: boolean;
  forced: boolean;
  hearing_impaired: boolean;
  commentary: boolean;
  bit_rate: number | null;
  width: number | null;
  height: number | null;
  bit_depth: number | null;
  frame_rate: number | null;
  hdr: string | null;
  channels: number | null;
  channel_layout: string | null;
  sample_rate: number | null;
  image_based: boolean;
}

export interface FileDetail extends FileSummary {
  path: string;
  container: string | null;
  bit_rate: number | null;
  streams: Stream[];
  probed_at: string | null;
}

export function useScanStatus(libraryId: number, poll: boolean) {
  return useQuery({
    queryKey: ['scan', libraryId],
    queryFn: () => api<ScanStatus | null>(`libraries/${libraryId}/scan`),
    refetchInterval: poll ? 1000 : false,
  });
}

export function useStartScan(libraryId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api<{ started: boolean }>(`libraries/${libraryId}/scan`, { method: 'POST' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['scan', libraryId] }),
  });
}

export function useFiles(
  libraryId: number,
  params: { q: string; problems: boolean; page: number; pageSize: number },
) {
  const search = new URLSearchParams({
    q: params.q,
    problems: String(params.problems),
    offset: String((params.page - 1) * params.pageSize),
    limit: String(params.pageSize),
  });
  return useQuery({
    queryKey: ['files', libraryId, params],
    queryFn: () =>
      api<{ total: number; items: FileSummary[] }>(`libraries/${libraryId}/files?${search}`),
    placeholderData: (previous) => previous,
  });
}

export function useFile(fileId: number | null) {
  return useQuery({
    queryKey: ['file', fileId],
    queryFn: () => api<FileDetail>(`files/${fileId}`),
    enabled: fileId !== null,
  });
}
