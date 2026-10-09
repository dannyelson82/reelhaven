// Find my sweet spot (ADR-0031): one scene of a file encoded at several qualities.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, json } from './client';
import { liveConnected } from './live';
import type { ProfileSettings } from './profiles';

export interface TuneResult {
  /** The whole file now, and its estimated size at this quality. */
  bytes_before: number;
  bytes_after: number;
  savings_percent: number | null;
  scene_bytes_before: number;
  scene_bytes_after: number;
  xpsnr: number | null;
  ssim: number | null;
  rating: string;
  frame_times: number[];
  clip: { start: number; seconds: number } | null;
  codec: string;
  bit_depth: number | null;
  height_after: number | null;
  hdr: string | null;
  device: string;
  fps: number | null;
  seconds: number;
}

export interface TuneStep {
  id: number;
  quality: number;
  status: 'queued' | 'running' | 'done' | 'failed';
  result: TuneResult | null;
  error: string | null;
  progress: number;
  job_id: number | null;
  fps: number | null;
}

export interface TuneSession {
  id: number;
  file: string;
  media_file_id: number | null;
  /** Null for a test film, which belongs to no library. */
  library_id: number | null;
  film_id: string | null;
  base: ProfileSettings;
  scene_start: number;
  scene_seconds: number;
  file_bytes: number;
  /** Best quality first. */
  steps: TuneStep[];
  created_at: string;
}

const busy = (session?: TuneSession) =>
  session?.steps.some((s) => s.status === 'queued' || s.status === 'running') ?? false;

export function useTuneSessions() {
  return useQuery({ queryKey: ['tune'], queryFn: () => api<TuneSession[]>('tune-sessions') });
}

export function useTuneSession(id: number | null) {
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: ['tune', id],
    queryFn: () => api<TuneSession>(`tune-sessions/${id}`),
    enabled: id !== null,
    refetchInterval: (q) =>
      !busy(q.state.data) ? false : liveConnected(queryClient) ? 5000 : 1500,
  });
}

function useTuneMutation<TBody>(request: (body: TBody) => Promise<TuneSession | null>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: request,
    onSuccess: (session) => {
      if (session) queryClient.setQueryData(['tune', session.id], session);
      void queryClient.invalidateQueries({ queryKey: ['tune'], exact: true });
      void queryClient.invalidateQueries({ queryKey: ['jobs'] });
    },
  });
}

export const useStartTune = () =>
  useTuneMutation((body: { file_id?: number; film_id?: string; settings: ProfileSettings }) =>
    api<TuneSession>('tune-sessions', { method: 'POST', body: json(body) }),
  );

export const useAddTuneStep = (sessionId: number) =>
  useTuneMutation((quality: number) =>
    api<TuneSession>(`tune-sessions/${sessionId}/steps`, {
      method: 'POST',
      body: json({ quality }),
    }),
  );

export const useDeleteTune = () =>
  useTuneMutation(async (sessionId: number) => {
    await api<null>(`tune-sessions/${sessionId}`, { method: 'DELETE' });
    return null;
  });

export const tuneFrameUrl = (stepId: number, index: number, which: 'source' | 'encoded') =>
  `api/v1/tune-steps/${stepId}/frames/${index}/${which}`;

export const tuneClipUrl = (stepId: number, which: 'source' | 'encoded') =>
  `api/v1/tune-steps/${stepId}/clips/${which}`;

/** Qualities worth trying next to the ones tried so far: one step past each end, and the
 * half-way point of each gap of a whole level or more (rounded to a half step). */
export function nextQualities(tried: number[]): {
  better: number | null;
  smaller: number | null;
  between: [number, number, number][];
} {
  const sorted = [...new Set(tried)].sort((a, b) => b - a);
  if (sorted.length === 0) return { better: null, smaller: null, between: [] };
  const top = sorted[0];
  const bottom = sorted[sorted.length - 1];
  const between: [number, number, number][] = [];
  for (let i = 0; i + 1 < sorted.length; i++) {
    const [high, low] = [sorted[i], sorted[i + 1]];
    if (high - low >= 1) between.push([high, low, Math.round(high + low) / 2]);
  }
  return {
    better: top < 10 ? Math.min(10, top + 1) : null,
    smaller: bottom > 1 ? Math.max(1, bottom - 1) : null,
    between,
  };
}
