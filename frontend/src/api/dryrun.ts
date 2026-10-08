import { useQuery } from '@tanstack/react-query';
import { api } from './client';

export type DryRunShow = 'changes' | 'flagged' | 'all';

export interface DryRunItem {
  file_id: number;
  relative_path: string;
  size: number;
  original_language: string | null;
  action: 'encode' | 'remux' | 'skip' | 'unreadable';
  flags: string[];
  summary: string;
  details: string[];
  removed_bytes: number | null;
  bytes_after_estimate: number | null;
  savings_percent: number | null;
  language_pending: boolean;
}

export interface DryRunResult {
  files: number;
  encode: number;
  remux: number;
  unchanged: number;
  unreadable: number;
  flags: Record<string, number>;
  unknown_original: number;
  saved_bytes: number;
  savings_unknown: number;
  waiting_for_language: number;
  total: number;
  items: DryRunItem[];
}

export function useDryRun(libraryId: number, show: DryRunShow, page: number, enabled: boolean) {
  const pageSize = 100;
  return useQuery({
    queryKey: ['dry-run', libraryId, show, page],
    queryFn: () =>
      api<DryRunResult>(
        `libraries/${libraryId}/dry-run?show=${show}&offset=${(page - 1) * pageSize}&limit=${pageSize}`,
      ),
    enabled,
    placeholderData: (previous) => previous,
  });
}
