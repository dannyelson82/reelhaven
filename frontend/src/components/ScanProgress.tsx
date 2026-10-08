// A running scan: what it's doing, how far along it is and the time left.
import { Group, Progress, Stack, Text } from '@mantine/core';
import type { ScanStatus } from '../api/files';
import { formatTimeLeft } from '../format';

const count = (n: number) => n.toLocaleString();

function describe(status: ScanStatus): { label: string; done: number; total: number } {
  switch (status.phase) {
    case 'listing':
      return {
        label:
          status.found > 0
            ? `Looking for video files… ${count(status.found)} found so far`
            : 'Looking for video files…',
        done: 0,
        total: 0,
      };
    case 'matching':
      return {
        label: `Checking for moved or renamed files: ${count(status.matched)} of ${count(status.to_match)}`,
        done: status.matched,
        total: status.to_match,
      };
    case 'probing':
      return {
        label: `Reading files: ${count(status.probed)} of ${count(status.to_probe)}`,
        done: status.probed,
        total: status.to_probe,
      };
    case 'languages':
      return { label: 'Looking up original languages…', done: 0, total: 0 };
    default:
      return { label: 'Saving…', done: 0, total: 0 };
  }
}

export function ScanProgress({ status }: { status: ScanStatus }) {
  const { label, done, total } = describe(status);
  const measured = total > 0;
  return (
    <Stack gap={4}>
      <Group justify="space-between" wrap="nowrap">
        <Text size="sm">{label}</Text>
        {status.eta_seconds != null && (
          <Text size="sm" c="dimmed" style={{ whiteSpace: 'nowrap' }}>
            about {formatTimeLeft(status.eta_seconds)} left
          </Text>
        )}
      </Group>
      <Progress
        value={measured ? (100 * done) / total : 100}
        striped={!measured}
        animated={!measured}
        aria-label={label}
      />
    </Stack>
  );
}
