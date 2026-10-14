import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, json } from './client';

export interface AutomationSettings {
  paused: boolean;
  rescan_enabled: boolean;
  rescan_at: string; // "HH:MM", local time
}

const KEY = ['automation'];

export function useAutomation() {
  return useQuery({
    queryKey: KEY,
    queryFn: () => api<AutomationSettings>('automation'),
    refetchInterval: 30000,
  });
}

export function useSaveAutomation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (settings: AutomationSettings) =>
      api<AutomationSettings>('automation', { method: 'PUT', body: json(settings) }),
    onSuccess: (saved) => {
      queryClient.setQueryData(KEY, saved);
      void queryClient.invalidateQueries({ queryKey: ['jobs'] });
    },
  });
}

/** Processing stopped because a disk is full; it carries on by itself once there's room. */
export interface SpaceHold {
  since: string;
  error: string;
  needed_bytes: number;
  disks: { path: string; free_bytes: number }[];
}

const HOLD_KEY = ['automation', 'space-hold'];

export function useSpaceHold() {
  return useQuery({
    queryKey: HOLD_KEY,
    queryFn: () => api<SpaceHold | null>('automation/space-hold'),
    refetchInterval: 15000,
  });
}

function useSpaceHoldMutation(request: () => Promise<SpaceHold | null>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: request,
    onSuccess: (hold) => {
      queryClient.setQueryData(HOLD_KEY, hold);
      void queryClient.invalidateQueries({ queryKey: ['jobs'] });
    },
  });
}

export const useCheckSpace = () =>
  useSpaceHoldMutation(() =>
    api<SpaceHold | null>('automation/space-hold/check', { method: 'POST' }),
  );

export const useResumeAnyway = () =>
  useSpaceHoldMutation(async () => {
    await api<void>('automation/space-hold', { method: 'DELETE' });
    return null;
  });
