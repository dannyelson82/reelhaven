// The review page (ADR-0032): files that need a decision.
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, json } from './client';

export type ReviewKind =
  'wrong_language' | 'failed' | 'unreadable' | 'skipped' | 'no_gain' | 'waiting';

export interface ReviewItem {
  kind: ReviewKind;
  file_id: number;
  library_id: number;
  library_name: string;
  relative_path: string;
  size: number;
  detail: string;
  ignored: boolean;
  job_id: number | null;
  original_language: string | null;
  audio_languages: string[];
}

export interface ReviewPage {
  counts: Record<ReviewKind, number>;
  ignored: number;
  total: number;
  items: ReviewItem[];
}

export const REVIEW_KINDS: { kind: ReviewKind; label: string; about: string }[] = [
  {
    kind: 'wrong_language',
    label: 'Wrong language',
    about: "None of the audio is in the library's languages: probably the wrong release.",
  },
  {
    kind: 'failed',
    label: 'Failed',
    about: "The file's last job failed; the original is unchanged.",
  },
  {
    kind: 'unreadable',
    label: "Can't be read",
    about: "ReelHaven couldn't read these files. They may be damaged or still being copied.",
  },
  {
    kind: 'skipped',
    label: 'Not re-encoded',
    about: 'Dolby Vision and HDR10+ are never re-encoded; languages are still handled.',
  },
  {
    kind: 'no_gain',
    label: 'No gain',
    about: "Re-encoding or converting the audio didn't make these smaller, so they were kept.",
  },
  {
    kind: 'waiting',
    label: 'Waiting',
    about: "The title's original language isn't known yet, so nothing changes until it is.",
  },
];

export function useReview(
  params: { kind?: ReviewKind; showIgnored?: boolean; page?: number } = {},
  pageSize = 100,
) {
  const query = new URLSearchParams();
  if (params.kind) query.set('kind', params.kind);
  if (params.showIgnored) query.set('show_ignored', 'true');
  query.set('offset', String(((params.page ?? 1) - 1) * pageSize));
  query.set('limit', String(pageSize));
  return useQuery({
    queryKey: ['review', params.kind ?? null, params.showIgnored ?? false, params.page ?? 1],
    queryFn: () => api<ReviewPage>(`review?${query.toString()}`),
    placeholderData: keepPreviousData,
    refetchInterval: 60_000,
  });
}

/** How many files need a decision (ignored ones and waiting ones left out), for the menu. */
export function useReviewCount(): number {
  const review = useReview({}, 1);
  const counts = review.data?.counts;
  if (!counts) return 0;
  return Object.entries(counts)
    .filter(([kind]) => kind !== 'waiting')
    .reduce((sum, [, n]) => sum + n, 0);
}

export function useIgnore() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { file_id: number; kind: ReviewKind; ignored: boolean }) =>
      api<null>('review/ignore', { method: 'PUT', body: json(body) }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['review'] }),
  });
}
