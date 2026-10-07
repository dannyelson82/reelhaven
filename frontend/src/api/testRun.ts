import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, json } from './client';

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
  return useQuery({
    queryKey: ['test-run', libraryId],
    queryFn: () => api<TestRunState>(`libraries/${libraryId}/test-run`),
    refetchInterval: (q) => (q.state.data?.run?.status === 'running' ? 1500 : false),
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
  `api/v1/test-run-samples/${sampleId}/frames/${index}/${which}.jpg`;
