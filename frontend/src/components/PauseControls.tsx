import { Alert, Button } from '@mantine/core';
import { IconPlayerPause, IconPlayerPlay } from '@tabler/icons-react';
import { errorMessage } from '../api/client';
import { useAutomation, useSaveAutomation } from '../api/automation';

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
