import { Alert, Button, Code, Group, Stack, Text } from '@mantine/core';
import { IconPlayerPause, IconPlayerPlay } from '@tabler/icons-react';
import { errorMessage } from '../api/client';
import {
  useAutomation,
  useCheckSpace,
  useResumeAnyway,
  useSaveAutomation,
  useSpaceHold,
} from '../api/automation';
import { formatBytes } from '../format';

/** Pause / resume all processing (ADR-0025): running jobs finish, nothing new starts. */
export function PauseButton() {
  const automation = useAutomation();
  const save = useSaveAutomation();
  if (!automation.data) return null;
  const paused = automation.data.paused;
  return (
    <Button
      variant={paused ? 'filled' : 'default'}
      color={paused ? 'teal' : undefined}
      leftSection={paused ? <IconPlayerPlay size={16} /> : <IconPlayerPause size={16} />}
      loading={save.isPending}
      onClick={() => automation.data && save.mutate({ ...automation.data, paused: !paused })}
    >
      {paused ? 'Resume processing' : 'Pause all processing'}
    </Button>
  );
}

export function PausedBanner() {
  const automation = useAutomation();
  const save = useSaveAutomation();
  if (!automation.data?.paused) return null;
  return (
    <Alert color="orange" title="Processing is paused">
      Jobs that were running finish; nothing new starts, manual or automatic, until you resume.{' '}
      <Button
        size="xs"
        variant="light"
        ml="xs"
        loading={save.isPending}
        onClick={() => automation.data && save.mutate({ ...automation.data, paused: false })}
      >
        Resume
      </Button>
      {save.isError && <div>{errorMessage(save.error)}</div>}
    </Alert>
  );
}

/** Shown while a full disk holds up all work; it lifts by itself once there's room. */
export function DiskFullBanner() {
  const hold = useSpaceHold();
  const check = useCheckSpace();
  const resume = useResumeAnyway();
  const data = hold.data;
  if (!data) return null;
  const short = data.disks.filter((disk) => disk.free_bytes < data.needed_bytes);
  return (
    <Alert color="red" title="Processing stopped: a disk is full">
      <Stack gap={6}>
        <Text size="sm">
          A job ran out of disk space, so nothing new starts. The job goes back in the queue and
          your original file wasn't changed. ReelHaven checks every 30 seconds and carries on by
          itself once each disk has {formatBytes(data.needed_bytes)} free.
        </Text>
        {short.map((disk) => (
          <Text size="sm" key={disk.path}>
            <Code>{disk.path}</Code>: {formatBytes(disk.free_bytes)} free
          </Text>
        ))}
        <Text size="xs" c="dimmed">
          {data.error}
        </Text>
        <Group gap="xs">
          <Button
            size="xs"
            variant="light"
            loading={check.isPending}
            onClick={() => check.mutate()}
          >
            Check now
          </Button>
          <Button
            size="xs"
            variant="subtle"
            color="gray"
            loading={resume.isPending}
            onClick={() => resume.mutate()}
          >
            Carry on anyway
          </Button>
        </Group>
        {check.data && check.isSuccess && (
          <Text size="sm">Still not enough room; free up some space and check again.</Text>
        )}
        {(check.isError || resume.isError) && (
          <Text size="sm">{errorMessage(check.error ?? resume.error)}</Text>
        )}
      </Stack>
    </Alert>
  );
}
