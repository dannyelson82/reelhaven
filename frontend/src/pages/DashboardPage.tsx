import { Anchor, Card, Group, Progress, Stack, Text, Title } from '@mantine/core';
import { Link } from 'react-router';
import { useJobs } from '../api/jobs';
import { useLiveJobs, withLive } from '../api/live';
import { PausedBanner } from '../components/PauseControls';
import { formatTimeLeft } from '../format';

export function DashboardPage() {
  return (
    <Stack maw={960}>
      <Title order={2}>Dashboard</Title>
      <PausedBanner />
      <ActiveJobs />
    </Stack>
  );
}

function ActiveJobs() {
  const jobs = useJobs('active', 1);
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
              {Math.round(job.progress * 100)}%{job.device && ` · ${job.device}`}
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
