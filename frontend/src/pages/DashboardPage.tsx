import { Anchor, Button, Card, Group, Progress, Stack, Text, Title } from '@mantine/core';
import { IconWand } from '@tabler/icons-react';
import { Link, Navigate } from 'react-router';
import { useDeviceName } from '../api/devices';
import { useJobs } from '../api/jobs';
import { useLibraries } from '../api/libraries';
import { useOnboarding } from '../api/wizard';
import { useLiveJobs, withLive } from '../api/live';
import { PausedBanner } from '../components/PauseControls';
import { SavingsCard } from '../components/SavingsCard';
import { formatTimeLeft } from '../format';

export function DashboardPage() {
  const libraries = useLibraries();
  const onboarding = useOnboarding();
  const empty = libraries.data?.length === 0;
  // First visit after setup: open the wizard once (ADR-0026).
  if (empty && onboarding.data && !onboarding.data.wizard_seen)
    return <Navigate to="/wizard" replace />;
  return (
    <Stack maw={960}>
      <Title order={2}>Dashboard</Title>
      <PausedBanner />
      {empty && (
        <Card withBorder padding="lg">
          <Stack align="flex-start">
            <Title order={4}>Welcome to ReelHaven</Title>
            <Text>
              The setup wizard walks you through making a library smaller, step by step, and then
              keeps it that way automatically.
            </Text>
            <Button component={Link} to="/wizard" leftSection={<IconWand size={16} />}>
              Set up your first library
            </Button>
          </Stack>
        </Card>
      )}
      <ActiveJobs />
      <SavingsCard />
      <Anchor component={Link} to="/stats" size="sm">
        Speed and results for each graphics card, and jobs per day, are on the Stats page.
      </Anchor>
    </Stack>
  );
}

function ActiveJobs() {
  const jobs = useJobs('active', 1);
  const deviceName = useDeviceName();
  const live = useLiveJobs();
  const running = (jobs.data?.items ?? [])
    .map((job) => withLive(job, live))
    .filter((job) => job.status === 'running' || job.status === 'verifying');
  const queued = (live?.counts ?? jobs.data?.counts ?? {}).queued ?? 0;
  if (!jobs.data) return null;
  if (running.length === 0 && queued === 0) {
    return (
      <Text c="dimmed">
        Nothing is being processed right now. Libraries are on the{' '}
        <Anchor component={Link} to="/libraries">
          Libraries
        </Anchor>{' '}
        page.
      </Text>
    );
  }
  return (
    <Card withBorder>
      <Stack gap="sm">
        <Group justify="space-between">
          <Title order={4}>In progress</Title>
          <Anchor component={Link} to="/jobs" size="sm">
            All jobs
          </Anchor>
        </Group>
        {running.map((job) => (
          <Stack key={job.id} gap={2}>
            <Text size="sm" fw={500} style={{ wordBreak: 'break-word' }}>
              {job.file}
            </Text>
            <Progress value={job.progress * 100} animated />
            <Text size="xs" c="dimmed">
              {Math.round(job.progress * 100)}%{job.device && ` · ${deviceName(job.device)}`}
              {job.decoder && ` · decoded on ${job.decoder.toUpperCase()}`}
              {job.fps !== null && ` · ${job.fps.toFixed(0)} fps`}
              {job.speed !== null && ` · ${job.speed.toFixed(1)}× real time`}
              {job.eta_seconds !== null && ` · ${formatTimeLeft(job.eta_seconds)} left`}
            </Text>
          </Stack>
        ))}
        {queued > 0 && (
          <Text size="sm" c="dimmed">
            {queued} more {queued === 1 ? 'file is' : 'files are'} waiting.
          </Text>
        )}
      </Stack>
    </Card>
  );
}
