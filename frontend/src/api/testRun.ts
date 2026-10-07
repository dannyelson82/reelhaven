import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, json } from './client';

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

export interface TestRun {
  id: number;
  status: 'running' | 'done' | 'failed' | 'approved';
  file: string | null;
  media_file_id: number | null;
  profile: Record<string, unknown>;
  profile_is_current: boolean;
  result: TestRunResult | null;
  error: string | null;
  progress: number;
  job_status: string | null;
  fps: number | null;
  created_at: string;
  finished_at: string | null;
  approved_by: string | null;
  approved_at: string | null;
}

export function useTestRun(libraryId: number) {
  return useQuery({
    queryKey: ['test-run', libraryId],
    queryFn: () => api<TestRun | null>(`libraries/${libraryId}/test-run`),
    refetchInterval: (q) => (q.state.data?.status === 'running' ? 1500 : false),
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
  useTestRunMutation(libraryId, (fileId: number | null) =>
    api<TestRun>(`libraries/${libraryId}/test-run`, {
      method: 'POST',
      body: json({ file_id: fileId }),
    }),
  );

export const useApproveTestRun = (libraryId: number) =>
  useTestRunMutation(libraryId, (runId: number) =>
    api<TestRun>(`test-runs/${runId}/approve`, { method: 'POST' }),
  );

export const frameUrl = (runId: number, index: number, which: 'source' | 'encoded') =>
  `api/v1/test-runs/${runId}/frames/${index}/${which}.jpg`;
