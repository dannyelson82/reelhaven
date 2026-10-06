import {
  Alert,
  Breadcrumbs,
  Anchor,
  Loader,
  NavLink,
  ScrollArea,
  Stack,
  Text,
} from '@mantine/core';
import { IconFolder } from '@tabler/icons-react';
import { useBrowse } from '../api/libraries';
import { errorMessage } from '../api/client';

/** Browse folders inside /media. `value` is a path relative to the media root. */
export function FolderPicker({
  value,
  onChange,
}: {
  value: string;
  onChange: (path: string) => void;
}) {
  const browse = useBrowse(value, true);
  const parts = value ? value.split('/') : [];

  return (
    <Stack gap="xs">
      <Breadcrumbs separator="/">
        <Anchor component="button" type="button" onClick={() => onChange('')}>
          media
        </Anchor>
        {parts.map((part, i) => (
          <Anchor
            key={i}
            component="button"
            type="button"
            onClick={() => onChange(parts.slice(0, i + 1).join('/'))}
          >
            {part}
          </Anchor>
        ))}
      </Breadcrumbs>
      <ScrollArea
        h={220}
        type="auto"
        style={{
          border: '1px solid var(--mantine-color-default-border)',
          borderRadius: 'var(--mantine-radius-md)',
        }}
      >
        {browse.isPending && <Loader size="sm" m="sm" />}
        {browse.isError && (
          <Alert color="red" m="xs">
            {errorMessage(browse.error)}
          </Alert>
        )}
        {browse.data?.parent !== null && browse.data !== undefined && (
          <NavLink
            component="button"
            type="button"
            label=".."
            onClick={() => onChange(browse.data.parent ?? '')}
          />
        )}
        {browse.data?.dirs.map((dir) => (
          <NavLink
            component="button"
            type="button"
            key={dir.path}
            label={dir.name}
            leftSection={<IconFolder size={16} />}
            onClick={() => onChange(dir.path)}
          />
        ))}
        {browse.data && browse.data.dirs.length === 0 && (
          <Text size="sm" c="dimmed" p="sm">
            No sub-folders here.
          </Text>
        )}
      </ScrollArea>
    </Stack>
  );
}
