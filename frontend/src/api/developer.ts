// Developer options (ADR-0033): shows the report downloads.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, json } from './client';

export interface DeveloperSettings {
  enabled: boolean;
}

const KEY = ['developer-settings'];

export const FAILURE_REPORT_URL = 'api/v1/reports/failures';
export const REVIEW_REPORT_URL = 'api/v1/reports/review';

export function useDeveloperSettings() {
  return useQuery({ queryKey: KEY, queryFn: () => api<DeveloperSettings>('settings/developer') });
}

/** Whether the report buttons show; false until the setting has loaded. */
export function useDeveloperOptions(): boolean {
  return useDeveloperSettings().data?.enabled ?? false;
}

export function useSaveDeveloperSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (settings: DeveloperSettings) =>
      api<DeveloperSettings>('settings/developer', { method: 'PUT', body: json(settings) }),
    onSuccess: (saved) => queryClient.setQueryData(KEY, saved),
  });
}
