import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, json } from './client';

export type LibraryType = 'movies' | 'tv' | 'other';

export interface Library {
  id: number;
  name: string;
  type: LibraryType;
  path: string;
  relative_path: string;
  created_at: string;
  file_count: number;
  last_scan_at: string | null;
  last_scan_error: string | null;
  scanning: boolean;
}

export interface BrowseResult {
  path: string;
  parent: string | null;
  dirs: { name: string; path: string }[];
  truncated: boolean;
}

export const LIBRARY_TYPES: { value: LibraryType; label: string }[] = [
  { value: 'movies', label: 'Movies' },
  { value: 'tv', label: 'TV shows' },
  { value: 'other', label: 'Other videos' },
];

const LIBRARIES_KEY = ['libraries'] as const;

export function useLibraries() {
  return useQuery({ queryKey: LIBRARIES_KEY, queryFn: () => api<Library[]>('libraries') });
}

export function useBrowse(path: string, enabled: boolean) {
  return useQuery({
    queryKey: ['browse', path],
    queryFn: () => api<BrowseResult>(`browse?path=${encodeURIComponent(path)}`),
    enabled,
  });
}

function useLibraryMutation<TBody, TResult>(request: (body: TBody) => Promise<TResult>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: request,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: LIBRARIES_KEY }),
  });
}

export const useCreateLibrary = () =>
  useLibraryMutation((body: { name: string; type: LibraryType; path: string }) =>
    api<Library>('libraries', { method: 'POST', body: json(body) }),
  );

export const useUpdateLibrary = () =>
  useLibraryMutation(({ id, ...body }: { id: number; name: string; type: LibraryType }) =>
    api<Library>(`libraries/${id}`, { method: 'PATCH', body: json(body) }),
  );

export const useDeleteLibrary = () =>
  useLibraryMutation((id: number) => api(`libraries/${id}`, { method: 'DELETE' }));
