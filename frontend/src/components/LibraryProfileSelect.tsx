import { Select } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useLibraryProfile, useProfiles, useSetLibraryProfile } from '../api/profiles';

/** Which compression profile a library uses ("none" = languages only). */
export function LibraryProfileSelect({ libraryId }: { libraryId: number }) {
  const profiles = useProfiles();
  const current = useLibraryProfile(libraryId);
  const set = useSetLibraryProfile(libraryId);
  return (
    <Select
      aria-label="Compression profile"
      w={260}
      allowDeselect={false}
      disabled={!current.data || set.isPending}
      value={current.data ? String(current.data.profile_id ?? 'none') : null}
      data={[
        { value: 'none', label: 'No encoding (languages only)' },
        ...(profiles.data ?? []).map((p) => ({ value: String(p.id), label: `Encode: ${p.name}` })),
      ]}
      onChange={(value) =>
        set.mutate(value === 'none' || value === null ? null : Number(value), {
          onSuccess: () => notifications.show({ message: 'Compression profile saved.' }),
        })
      }
    />
  );
}
