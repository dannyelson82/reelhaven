import { useQuery } from '@tanstack/react-query';
import { api } from './client';

export interface WebhookLast {
  at: string;
  event: string;
  outcome: 'test' | 'rescan' | 'not_watched' | 'no_library' | 'ignored';
  message: string;
  library: string | null;
  path: string | null;
}

export function useWebhookStatus() {
  return useQuery({
    queryKey: ['webhooks'],
    queryFn: () => api<Record<'sonarr' | 'radarr', WebhookLast | null>>('webhooks'),
    refetchInterval: 15000,
  });
}

/** The address Sonarr/Radarr should call, as this browser sees ReelHaven. */
export function webhookUrl(kind: 'sonarr' | 'radarr'): string {
  return `${new URL(`api/v1/webhook/${kind}`, document.baseURI).toString()}?apikey=YOUR_API_KEY`;
}
