// Jobs → Upcoming: files that still need a job and aren't queued yet.
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { api } from './client';

export type UpcomingWhy = 'next' | 'test_run' | 'not_automatic';

export interface UpcomingItem {
  file_id: number;
  relative_path: string;
  action: 'encode' | 'remux' | 'quarantine' | 'delete';
  saved: number | null;
  why: UpcomingWhy;
  library_id: number;
  library_name: string;
}

export interface UpcomingPage {
  total: number;
  counts: Record<UpcomingWhy, number>;
  saved: number;
  items: UpcomingItem[];
}

export function useUpcoming(why: UpcomingWhy | null, page: number, enabled = true) {
  const query = new URLSearchParams({ offset: String((page - 1) * 50), limit: '50' });
  if (why) query.set('why', why);
  return useQuery({
    queryKey: ['upcoming', why, page],
    queryFn: () => api<UpcomingPage>(`upcoming?${query.toString()}`),
    enabled,
    placeholderData: keepPreviousData,
    refetchInterval: 30_000,
  });
}
