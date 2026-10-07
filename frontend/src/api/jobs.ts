import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, json } from './client';
import { liveConnected } from './live';

export interface Job {
  id: number;
  library_id: number;
  library_name: string | null;
  media_file_id: number | null;
  file: string;
  type: string;
  status: 'queued' | 'running' | 'verifying' | 'done' | 'failed' | 'cancelled';
  progress: number;
  summary: string;
  details: string[];
  error: string | null;
  requested_by: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  bytes_before: number | null;
  bytes_after: number | null;
  process_seconds: number | null;
  outcome: 'replaced' | 'no_gain' | null;
  device: string | null;
  fps: number | null;
  speed: number | null;
  eta_seconds: number | null;
}

export interface RecycleItem {
  id: number;
  library_id: number;
  original_path: string;
  size: number;
  reason: 'replaced' | 'restore-swap';
  job_id: number | null;
  created_at: string;
  expires_at: string;
  restored_at: string | null;
  purged_at: string | null;
}

export type JobFilter = 'active' | 'failed' | 'done' | 'all';

const ACTIVE = new Set(['queued', 'running', 'verifying']);
export const isActive = (job: Job) => ACTIVE.has(job.status);

export function useJobs(filter: JobFilter, page: number) {
  const queryClient = useQueryClient();
  return useQuery({
    queryKey: ['jobs', filter, page],
    queryFn: () =>
      api<{ total: number; counts: Record<string, number>; items: Job[] }>(
        `jobs?status=${filter}&offset=${(page - 1) * 50}&limit=50`,
      ),
    refetchInterval: (query) =>
      // The socket says when jobs change; polling is only the fallback.
      liveConnected(queryClient)
        ? 30000
        : query.state.data?.items.some(isActive) ||
            (query.state.data?.counts.queued ?? 0) + (query.state.data?.counts.running ?? 0) > 0
          ? 1500
          : 10000,
  });
}

function useJobMutation<TBody, TResult>(request: (body: TBody) => Promise<TResult>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: request,
    onSuccess: () => {
      for (const key of ['jobs', 'dry-run', 'files', 'plan', 'recycle']) {
        void queryClient.invalidateQueries({ queryKey: [key] });
      }
    },
  });
}

export const useApplyFile = () =>
  useJobMutation((fileId: number) => api<Job>(`files/${fileId}/apply`, { method: 'POST' }));

export const useApplyLibrary = () =>
  useJobMutation(({ libraryId, expected }: { libraryId: number; expected: number }) =>
    api<{ queued: number }>(`libraries/${libraryId}/apply`, {
      method: 'POST',
      body: json({ expected_count: expected }),
    }),
  );

export const useCancelJob = () =>
  useJobMutation((jobId: number) => api<Job>(`jobs/${jobId}/cancel`, { method: 'POST' }));

export const useRetryJob = () =>
  useJobMutation((jobId: number) => api<Job>(`jobs/${jobId}/retry`, { method: 'POST' }));

export function useRecycle(show: 'active' | 'all') {
  return useQuery({
    queryKey: ['recycle', show],
    queryFn: () => api<RecycleItem[]>(`recycle?show=${show}`),
  });
}

export const useRestore = () =>
  useJobMutation((itemId: number) =>
    api<RecycleItem>(`recycle/${itemId}/restore`, { method: 'POST' }),
  );

export const usePurge = () =>
  useJobMutation((itemId: number) => api(`recycle/${itemId}`, { method: 'DELETE' }));
