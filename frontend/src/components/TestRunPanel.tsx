import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Image,
  Loader,
  Progress,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { IconCheck, IconPlayerPlay } from '@tabler/icons-react';
import { errorMessage } from '../api/client';
import { useLibraryProfile } from '../api/profiles';
import {
  type TestRun,
  frameUrl,
  useApproveTestRun,
  useStartTestRun,
  useTestRun,
} from '../api/testRun';
import { formatBytes, formatDuration } from '../format';

const RATING_COLOR: Record<string, string> = {
  Indistinguishable: 'teal',
  'Very good': 'green',
  Good: 'yellow',
  'Visible loss': 'red',
  Unknown: 'gray',
};

export function TestRunPanel({ libraryId }: { libraryId: number }) {
  const profile = useLibraryProfile(libraryId);
  const run = useTestRun(libraryId);
  const start = useStartTestRun(libraryId);

  if (profile.isPending || run.isPending) return <Loader />;
  if (profile.data?.profile_id === null) {
    return (
      <Alert color="blue">
        Choose a compression profile for this library first (at the top of the page). Libraries
        without a profile only get language changes, which need no test run.
      </Alert>
    );
  }
  const current = run.data;
  return (
    <Stack>
      <Card withBorder>
        <Stack gap="xs">
          <Text size="sm">
            A test run re-encodes <b>one</b> file with this library's profile (the largest file that
            would be re-encoded), measures the quality and shows still frames side by side.{' '}
            <b>The original is never touched.</b> Re-encoding the whole library unlocks once you
            approve a test run with the current profile.
          </Text>
          <Group>
            <Button
              leftSection={<IconPlayerPlay size={16} />}
              loading={start.isPending}
              disabled={current?.status === 'running'}
              onClick={() => start.mutate(null)}
            >
              {current ? 'Start a new test run' : 'Start test run'}
            </Button>
          </Group>
          {start.isError && <Alert color="red">{errorMessage(start.error)}</Alert>}
        </Stack>
      </Card>
      {current && <TestRunResultView libraryId={libraryId} run={current} />}
    </Stack>
  );
}

function TestRunResultView({ libraryId, run }: { libraryId: number; run: TestRun }) {
  const approve = useApproveTestRun(libraryId);
  if (run.status === 'running') {
    return (
      <Card withBorder>
        <Stack gap="xs">
          <Text size="sm">
            Test-encoding <b>{run.file}</b>…{' '}
            {run.job_status === 'queued' && 'waiting for a free encoder'}
          </Text>
          <Progress value={run.progress * 100} animated />
          <Text size="xs" c="dimmed">
            {Math.round(run.progress * 100)}%{run.fps !== null && ` · ${run.fps.toFixed(0)} fps`}
          </Text>
        </Stack>
      </Card>
    );
  }
  if (run.status === 'failed' || !run.result) {
    return (
      <Alert color="red" title="The test run failed">
        <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>
          {run.error}
        </Text>
      </Alert>
    );
  }
  const r = run.result;
  const enough = r.savings_percent !== null && r.savings_percent >= r.min_savings_percent;
  return (
    <Stack>
      {!run.profile_is_current && (
        <Alert color="yellow">
          The profile changed since this test run. Start a new one to approve it.
        </Alert>
      )}
      <Card withBorder>
        <Stack gap="sm">
          <Group justify="space-between">
            <Title order={4}>{run.file}</Title>
            <Badge size="lg" color={RATING_COLOR[r.rating] ?? 'gray'}>
              {r.rating}
            </Badge>
          </Group>
          <SimpleGrid cols={{ base: 2, sm: 4 }}>
            <Fact
              label="Size"
              value={`${formatBytes(r.bytes_before)} → ${formatBytes(r.bytes_after)}`}
            />
            <Fact
              label="Saved"
              value={r.savings_percent !== null ? `${r.savings_percent}%` : '?'}
              color={enough ? 'teal' : 'red'}
            />
            <Fact
              label="Quality"
              value={
                [r.xpsnr !== null && `XPSNR ${r.xpsnr} dB`, r.ssim !== null && `SSIM ${r.ssim}`]
                  .filter(Boolean)
                  .join(' · ') || '–'
              }
            />
            <Fact
              label="Video"
              value={`${r.codec.toUpperCase()} ${r.bit_depth ?? ''}-bit ${r.height_after ?? ''}p${r.hdr && r.hdr !== 'sdr' ? ` ${r.hdr.toUpperCase()}` : ''}`}
            />
          </SimpleGrid>
          <Text size="xs" c="dimmed">
            Encoded on {r.device}
            {r.fps !== null && ` at ${r.fps.toFixed(0)} fps`} in {formatDuration(r.seconds)}.
          </Text>
          {!enough && (
            <Alert color="orange">
              This saves less than the profile's {r.min_savings_percent}% minimum, so a real encode
              of this file would keep the original. Consider a smaller profile.
            </Alert>
          )}
        </Stack>
      </Card>
      {r.frame_times.map((at, index) => (
        <Card key={index} withBorder>
          <Text size="sm" fw={500} mb="xs">
            At {formatDuration(at)}
          </Text>
          <SimpleGrid cols={{ base: 1, md: 2 }}>
            <Stack gap={4}>
              <Text size="xs" c="dimmed">
                Original
              </Text>
              <Image
                src={frameUrl(run.id, index, 'source')}
                alt={`Original at ${at}s`}
                radius="sm"
              />
            </Stack>
            <Stack gap={4}>
              <Text size="xs" c="dimmed">
                Re-encoded
              </Text>
              <Image
                src={frameUrl(run.id, index, 'encoded')}
                alt={`Re-encoded at ${at}s`}
                radius="sm"
              />
            </Stack>
          </SimpleGrid>
        </Card>
      ))}
      {r.hdr && r.hdr !== 'sdr' && (
        <Text size="xs" c="dimmed">
          HDR stills look washed out in a browser; judge colours on your TV.
        </Text>
      )}
      {run.status === 'approved' ? (
        <Alert color="teal" icon={<IconCheck />}>
          Approved by {run.approved_by} on{' '}
          {run.approved_at && new Date(run.approved_at).toLocaleString()}. Re-encoding this library
          is unlocked.
        </Alert>
      ) : (
        <Group>
          <Button
            color="teal"
            leftSection={<IconCheck size={16} />}
            disabled={!run.profile_is_current}
            loading={approve.isPending}
            onClick={() =>
              approve.mutate(run.id, {
                onSuccess: () =>
                  notifications.show({ message: 'Approved. You can now re-encode this library.' }),
              })
            }
          >
            Looks good: allow re-encoding this library
          </Button>
          {approve.isError && (
            <Text size="sm" c="red">
              {errorMessage(approve.error)}
            </Text>
          )}
        </Group>
      )}
    </Stack>
  );
}

function Fact({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <Stack gap={0}>
      <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
        {label}
      </Text>
      <Text size="sm" fw={600} c={color}>
        {value}
      </Text>
    </Stack>
  );
}
