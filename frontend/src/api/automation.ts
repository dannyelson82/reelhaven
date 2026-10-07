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
