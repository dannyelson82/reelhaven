import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, json } from './client';

export interface CodecResult {
  codec: 'hevc' | 'av1' | 'h264';
  ten_bit: boolean;
  encoder: string;
  ok: boolean;
  error: string | null;
  seconds: number | null;
}

export interface DeviceInfo {
  id: string;
  kind: 'nvidia' | 'intel' | 'amd' | 'cpu';
  name: string;
  family: string;
  results: CodecResult[];
  enabled: boolean;
  concurrency: number;
}

export interface DeviceSettings {
  cpu_enabled: boolean;
  cpu_concurrency: number;
  devices: Record<string, { enabled: boolean; concurrency: number }>;
  /** CPU limiter: at most this many cores for everything ReelHaven runs; null: all. */
  cpu_cores?: number | null;
}

export interface DevicesResponse {
  detecting: boolean;
  detected_at: number | null;
  devices: DeviceInfo[];
  settings: DeviceSettings;
  /** Cores this container may use. */
  cpu_cores_available?: number;
}

const KEY = ['devices'] as const;

export function useDevices() {
  return useQuery({
    queryKey: KEY,
    queryFn: () => api<DevicesResponse>('devices'),
    refetchInterval: (q) => (q.state.data?.detecting || !q.state.data?.detected_at ? 1500 : false),
  });
}

export function useDetectDevices() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api<DevicesResponse>('devices/detect', { method: 'POST' }),
    onSuccess: (data) => queryClient.setQueryData(KEY, data),
  });
}

export function useSaveDeviceSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (settings: DeviceSettings) =>
      api<DevicesResponse>('devices/settings', { method: 'PUT', body: json(settings) }),
    onSuccess: (data) => queryClient.setQueryData(KEY, data),
  });
}

/** A device's display name ("NVIDIA GeForce RTX 3060") from its id ("nvidia:0"). */
export function useDeviceName(): (id: string | null | undefined) => string | null {
  const devices = useDevices();
  return (id) => (id ? (devices.data?.devices.find((d) => d.id === id)?.name ?? id) : null);
}
