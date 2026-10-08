import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Loader,
  Modal,
  Stack,
  Switch,
  Text,
  Title,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useState } from 'react';
import { errorMessage } from '../api/client';
import { type RecycleItem, usePurge, useRecycle, useRestore } from '../api/jobs';
import { type KeepDays, useRecycleSettings, useSaveRecycleSettings } from '../api/recycleSettings';
import { KeepOriginalsControl } from '../components/KeepOriginals';
import { formatBytes } from '../format';

export function RecyclePage() {
  const [showAll, setShowAll] = useState(false);
  const items = useRecycle(showAll ? 'all' : 'active');
  const [purging, setPurging] = useState<RecycleItem | null>(null);
  const purge = usePurge();
  const total = (items.data ?? [])
    .filter((i) => !i.restored_at && !i.purged_at)
    .reduce((sum, i) => sum + i.size, 0);

  return (
    <Stack maw={960}>
      <Title order={2}>Recycle bin</Title>
      <Text size="sm" c="dimmed">
        Files ReelHaven replaces are kept here, on the same disk as your library, in a hidden{' '}
        <code>.reelhaven</code> folder. Restoring puts a file back exactly as it was.
      </Text>
      <KeepSetting />
      <Group justify="space-between">
        <Text size="sm">Using {formatBytes(total)}</Text>
        <Switch
          label="Show restored and deleted items"
          checked={showAll}
          onChange={(e) => setShowAll(e.currentTarget.checked)}
        />
      </Group>
      {items.isPending && <Loader />}
      {items.isError && <Alert color="red">{errorMessage(items.error)}</Alert>}
      {items.data?.length === 0 && (
        <Card withBorder>
          <Text c="dimmed">The recycle bin is empty.</Text>
        </Card>
      )}
      {items.data?.map((item) => (
        <RecycleCard key={item.id} item={item} onPurge={() => setPurging(item)} />
      ))}
      <Modal opened={purging !== null} onClose={() => setPurging(null)} title="Delete for good?">
        <Stack>
          <Text size="sm">
            <b>{purging?.original_path.split('/').pop()}</b> ({formatBytes(purging?.size ?? 0)})
            will be permanently deleted. This can't be undone.
          </Text>
          {purge.isError && <Alert color="red">{errorMessage(purge.error)}</Alert>}
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setPurging(null)}>
              Keep it
            </Button>
            <Button
              color="red"
              loading={purge.isPending}
              onClick={() =>
                purging &&
                purge.mutate(purging.id, {
                  onSuccess: () => {
                    notifications.show({ message: 'Deleted.' });
                    setPurging(null);
                  },
                })
              }
            >
              Delete permanently
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}

function RecycleCard({ item, onPurge }: { item: RecycleItem; onPurge: () => void }) {
  const restore = useRestore();
  const gone = item.restored_at || item.purged_at;
  return (
    <Card withBorder>
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <Stack gap={2} style={{ minWidth: 0 }}>
          <Text fw={500} style={{ wordBreak: 'break-all' }}>
            {item.original_path}
          </Text>
          <Text size="xs" c="dimmed">
            {formatBytes(item.size)} ·{' '}
            {item.reason === 'replaced'
              ? `replaced by job #${item.job_id}`
              : 'version replaced by a restore'}{' '}
            · {new Date(item.created_at).toLocaleString()}
            {!gone && ` · deleted automatically ${new Date(item.expires_at).toLocaleDateString()}`}
          </Text>
          {item.restored_at && (
            <Badge color="teal" w="fit-content">
              Restored
            </Badge>
          )}
          {item.purged_at && (
            <Badge color="gray" w="fit-content">
              Deleted
            </Badge>
          )}
          {restore.isError && (
            <Text size="sm" c="red">
              {errorMessage(restore.error)}
            </Text>
          )}
        </Stack>
        {!gone && (
          <Group gap="xs" wrap="nowrap">
            <Button
              size="xs"
              loading={restore.isPending}
              onClick={() =>
                restore.mutate(item.id, {
                  onSuccess: () =>
                    notifications.show({
                      message: 'Restored. The version it replaced is now in the recycle bin.',
                    }),
                })
              }
            >
              Restore
            </Button>
            <Button size="xs" variant="subtle" color="red" onClick={onPurge}>
              Delete
            </Button>
          </Group>
        )}
      </Group>
    </Card>
  );
}

/** How long originals are kept (ADR-0028). Shortening it asks first; it only affects new files. */
function KeepSetting() {
  const setting = useRecycleSettings();
  const save = useSaveRecycleSettings();
  const [asking, setAsking] = useState<KeepDays | null>(null);
  if (!setting.data) return null;
  const current = setting.data.keep_days;
  const choose = (days: KeepDays) => {
    if (days === current) return;
    if (days < current) setAsking(days);
    else save.mutate({ keep_days: days });
  };
  return (
    <Card withBorder>
      <Stack gap="xs">
        <Text fw={500}>Keep originals for</Text>
        <KeepOriginalsControl value={current} onChange={choose} />
        {save.isError && <Alert color="red">{errorMessage(save.error)}</Alert>}
      </Stack>
      <Modal
        opened={asking !== null}
        onClose={() => setAsking(null)}
        title={asking === 0 ? 'Turn the recycle bin off?' : 'Keep originals for less time?'}
      >
        <Stack>
          <Text size="sm">
            {asking === 0
              ? "From now on, originals are deleted as soon as the new file passes its checks. They can't be restored."
              : `From now on, originals are kept for ${asking} ${asking === 1 ? 'day' : 'days'}.`}{' '}
            Files already in the bin keep their date; you can still delete them here.
          </Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setAsking(null)}>
              Cancel
            </Button>
            <Button
              color={asking === 0 ? 'red' : undefined}
              loading={save.isPending}
              onClick={() =>
                asking !== null &&
                save.mutate({ keep_days: asking }, { onSuccess: () => setAsking(null) })
              }
            >
              {asking === 0 ? 'Turn off' : 'Change'}
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Card>
  );
}
