import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, json } from './client';
import { liveConnected } from './live';

export const MAX_SAMPLES = 5;

export interface TestRunResult {
  bytes_before: number;
  bytes_after: number;
  savings_percent: number | null;
  min_savings_percent: number;
  xpsnr: number | null;
  ssim: number | null;
  rating: string;
  frame_times: number[];
  /** The comparison clips' scene (since 0.8); null if they couldn't be made. */
  clip?: { start: number; seconds: number } | null;
  codec: string;
  height_before: number | null;
  height_after: number | null;
  bit_depth: number | null;
  hdr: string | null;
  device: string;
  fps: number | null;
  seconds: number;
}

export interface TestSample {
  id: number;
  file: string;
  media_file_id: number | null;
  status: 'running' | 'done' | 'failed';
  result: TestRunResult | null;
  error: string | null;
  progress: number;
  job_id: number | null;
  job_status: string | null;
  fps: number | null;
}

export interface TestRun {
  id: number;
  status: 'running' | 'done' | 'failed' | 'approved';
  profile: Record<string, unknown>;
  profile_is_current: boolean;
  samples: TestSample[];
  created_at: string;
  finished_at: string | null;
  approved_by: string | null;
  approved_at: string | null;
}

export interface TestRunState {
  samples: number;
  run: TestRun | null;
}

export function useTestRun(libraryId: number) {
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: ['test-run', libraryId],
    queryFn: () => api<TestRunState>(`libraries/${libraryId}/test-run`),
    refetchInterval: (q) =>
      q.state.data?.run?.status !== 'running' ? false : liveConnected(queryClient) ? 15000 : 1500,
  });
}

function useTestRunMutation<TBody, TResult>(
  libraryId: number,
  request: (body: TBody) => Promise<TResult>,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: request,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['test-run', libraryId] });
      void queryClient.invalidateQueries({ queryKey: ['jobs'] });
    },
  });
}

export const useStartTestRun = (libraryId: number) =>
  useTestRunMutation(libraryId, (samples: number) =>
    api<TestRun>(`libraries/${libraryId}/test-run`, {
      method: 'POST',
      body: json({ samples }),
    }),
  );

export const useApproveTestRun = (libraryId: number) =>
  useTestRunMutation(libraryId, (runId: number) =>
    api<TestRun>(`test-runs/${runId}/approve`, { method: 'POST' }),
  );

export const frameUrl = (sampleId: number, index: number, which: 'source' | 'encoded') =>
  `api/v1/test-run-samples/${sampleId}/frames/${index}/${which}`;

export const clipUrl = (sampleId: number, which: 'source' | 'encoded') =>
  `api/v1/test-run-samples/${sampleId}/clips/${which}`;

/** A sample's comparison clips for the viewer, if it has them. */
export function clipsOf(sampleId: number, clip: { start: number } | null | undefined) {
  return clip
    ? {
        source: clipUrl(sampleId, 'source'),
        encoded: clipUrl(sampleId, 'encoded'),
        start: clip.start,
      }
    : null;
}

/** Whether another sample of the run is encoding: samples go one at a time, so a queued
 * one is simply next in line. */
export function isUpNext(sample: TestSample, samples: TestSample[]): boolean {
  return (
    sample.job_status === 'queued' &&
    samples.some(
      (other) =>
        other.id !== sample.id &&
        (other.job_status === 'running' || other.job_status === 'verifying'),
    )
  );
}
