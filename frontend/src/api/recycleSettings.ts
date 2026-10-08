// How long replaced originals stay in the recycle bin (ADR-0028).
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, json } from './client';

export const KEEP_DAYS = [0, 1, 3, 7, 14, 30] as const;
export type KeepDays = (typeof KEEP_DAYS)[number];

export interface RecycleSettings {
  keep_days: KeepDays;
}

const KEY = ['recycle-settings'];

export function useRecycleSettings() {
  return useQuery({ queryKey: KEY, queryFn: () => api<RecycleSettings>('settings/recycle') });
}

export function useSaveRecycleSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (settings: RecycleSettings) =>
      api<RecycleSettings>('settings/recycle', { method: 'PUT', body: json(settings) }),
    onSuccess: (saved) => queryClient.setQueryData(KEY, saved),
  });
}

/** "for 14 days", "for 1 day"; null when the bin is off. */
export function keptFor(days: number): string | null {
  if (days === 0) return null;
  return `for ${days} ${days === 1 ? 'day' : 'days'}`;
}

/** One sentence about what happens to originals, for the places that mention it. */
export function originalsSentence(days: number | undefined): string {
  if (days === undefined || days > 0) {
    return `Originals go to the recycle bin ${keptFor(days ?? 14)} and can be restored.`;
  }
  return 'The recycle bin is off: originals are deleted once the new file passes its checks.';
}
