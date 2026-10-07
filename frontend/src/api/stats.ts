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
