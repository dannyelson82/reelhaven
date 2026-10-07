import { Button, Group, List, Modal, Select, Stack, Text } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useState } from 'react';
import { errorMessage } from '../api/client';
import { type Library, WATCH_MODES, type WatchMode, useSetWatchMode } from '../api/libraries';

/** Off / Watch / Automatic for one library (ADR-0025). Automatic asks first. */
export function WatchModeSelect({ library }: { library: Library }) {
  const set = useSetWatchMode();
  const [confirming, setConfirming] = useState(false);
  const save = (mode: WatchMode) =>
    set.mutate(
      { id: library.id, watch_mode: mode },
      {
        onSuccess: () => {
          setConfirming(false);
          notifications.show({
            message: `${library.name}: ${WATCH_MODES.find((m) => m.value === mode)?.label}.`,
          });
        },
        onError: (error) => notifications.show({ color: 'red', message: errorMessage(error) }),
      },
    );
  return (
    <>
      <Select
        aria-label="Watch mode"
        w={200}
        allowDeselect={false}
        disabled={set.isPending}
        value={library.watch_mode}
        data={WATCH_MODES.map((m) => ({ value: m.value, label: `Watch mode: ${m.label}` }))}
        onChange={(value) => {
          if (value === 'automatic') setConfirming(true);
          else if (value) save(value as WatchMode);
        }}
      />
      <Modal
        opened={confirming}
        onClose={() => setConfirming(false)}
        title="Process automatically?"
      >
        <Stack>
          <Text size="sm">
            ReelHaven will work through <b>every file in {library.name}</b> that needs changes,
            without asking, a few files at a time, and keep doing so as new files arrive.
          </Text>
          <List size="sm">
            <List.Item>
              Re-encoding only starts once a test run with the library&apos;s current profile is
              approved; track changes start straight away.
            </List.Item>
            <List.Item>
              Files that need review (wrong language, unreadable) are never touched.
            </List.Item>
            <List.Item>Every original still goes to the recycle bin for 14 days.</List.Item>
            <List.Item>You can pause all processing from the Jobs page at any time.</List.Item>
          </List>
          <Text size="sm">Tip: look at the Dry run tab first to see what it will do.</Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setConfirming(false)}>
              Cancel
            </Button>
            <Button loading={set.isPending} onClick={() => save('automatic')}>
              Switch to Automatic
            </Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}
