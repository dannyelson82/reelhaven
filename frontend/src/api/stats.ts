import { useQuery } from '@tanstack/react-query';
import { api } from './client';

export interface SavingsPeriod {
  start: string; // YYYY-MM-DD, local time
  saved: number;
  files: number;
}

export interface Savings {
  total_saved: number;
  files: number;
  this_week: number;
  this_month: number;
  weekly: SavingsPeriod[];
  monthly: SavingsPeriod[];
  libraries: { library_id: number; name: string; saved: number; files: number }[];
}

export function useSavings() {
  return useQuery({
    queryKey: ['savings'],
    queryFn: () => api<Savings>('stats/savings'),
    refetchInterval: 60_000,
  });
}

export interface DeviceStats {
  device: string;
  files: number;
  failed: number;
  saved: number;
  video_hours: number;
  work_hours: number;
  /** Hours of video per hour of work. */
  speed: number | null;
  fps: number | null;
  /** Share of encodes whose source the GPU decoded, 0 to 1. */
  gpu_decoded: number | null;
}

export interface DayStats {
  day: string; // YYYY-MM-DD, local time
  encoded: number;
  remuxed: number;
  failed: number;
  saved: number;
}

export interface Performance {
  devices: DeviceStats[];
  daily: DayStats[];
}

/** Per-device encodes over the last ``days`` days (0: all time), and jobs per day. */
export function usePerformance(days: number) {
  return useQuery({
    queryKey: ['performance', days],
    queryFn: () => api<Performance>(`stats/performance?days=${days}`),
    refetchInterval: 60_000,
  });
}
