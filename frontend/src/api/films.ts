// Test films (ADR-0031): open-licence films to try settings on, downloaded on request.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from './client';

export interface TestFilm {
  id: string;
  title: string;
  year: number;
  about: string;
  width: number;
  height: number;
  hdr: boolean;
  minutes: number;
  download_bytes: number;
  credit: string;
  licence: string;
  licence_url: string;
  source_url: string;
  state: 'available' | 'downloading' | 'verifying' | 'ready' | 'failed';
  downloaded_bytes: number;
  error: string | null;
}

const KEY = ['films'] as const;

export function useFilms(enabled = true) {
  return useQuery({
    queryKey: KEY,
    queryFn: () => api<TestFilm[]>('films'),
    enabled,
    refetchInterval: (q) =>
      q.state.data?.some((f) => f.state === 'downloading' || f.state === 'verifying')
        ? 1500
        : false,
  });
}

function useFilmMutation(request: (id: string) => Promise<TestFilm>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: request,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: KEY }),
  });
}

export const useDownloadFilm = () =>
  useFilmMutation((id) => api<TestFilm>(`films/${id}/download`, { method: 'POST' }));

export const useDeleteFilm = () =>
  useFilmMutation((id) => api<TestFilm>(`films/${id}`, { method: 'DELETE' }));
