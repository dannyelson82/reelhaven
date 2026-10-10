import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  List,
  Loader,
  Pagination,
  Progress,
  SegmentedControl,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { useState } from 'react';
import { errorMessage } from '../api/client';
import { useDeviceName } from '../api/devices';
import {
  type Job,
  type JobFilter,
  isActive,
  useCancelJob,
  useJobs,
  useRetryJob,
} from '../api/jobs';
import { useLiveJobs, withLive } from '../api/live';
import { type UpcomingItem, type UpcomingWhy, useUpcoming } from '../api/upcoming';
import { PauseButton, PausedBanner } from '../components/PauseControls';
import { formatBytes, formatTimeLeft } from '../format';

// Where the source video was decoded (ADR-0029).
const DECODER: Record<'gpu' | 'cpu', string> = { gpu: 'Decoded on GPU', cpu: 'Decoded on CPU' };

const STATUS: Record<Job['status'], { label: string; color: string }> = {
  queued: { label: 'Waiting', color: 'gray' },
  running: { label: 'Working', color: 'blue' },
  verifying: { label: 'Checking', color: 'cyan' },
  done: { label: 'Done', color: 'teal' },
  failed: { label: 'Failed', color: 'red' },
  cancelled: { label: 'Cancelled', color: 'gray' },
};

type View = JobFilter | 'upcoming';

export function JobsPage() {
  const [filter, setFilter] = useState<View>('all');
  const [page, setPage] = useState(1);
  const jobs = useJobs(filter === 'upcoming' ? 'all' : filter, page);
  const upcomingCount = useUpcoming(null, 1).data?.total;
  const live = useLiveJobs();
  const counts = live?.counts ?? jobs.data?.counts ?? {};
  const active = (counts.queued ?? 0) + (counts.running ?? 0) + (counts.verifying ?? 0);
  const failed = (counts.failed ?? 0) + (counts.cancelled ?? 0);

  return (
    <Stack maw={960}>
      <Group justify="space-between">
        <Title order={2}>Jobs</Title>
        <PauseButton />
      </Group>
      <PausedBanner />
      <SegmentedControl
        value={filter}
        onChange={(v) => {
          setFilter(v as View);
          setPage(1);
        }}
        data={[
          { value: 'all', label: 'All' },
          { value: 'active', label: `In progress (${active})` },
          { value: 'failed', label: `Failed (${failed})` },
          { value: 'done', label: `Done (${counts.done ?? 0})` },
          {
            value: 'upcoming',
            label: upcomingCount !== undefined ? `Upcoming (${upcomingCount})` : 'Upcoming',
          },
        ]}
        w="fit-content"
      />
      {filter === 'upcoming' ? (
        <UpcomingList />
      ) : (
        <JobList jobs={jobs} page={page} setPage={setPage} live={live} />
      )}
    </Stack>
  );
}

function JobList({
  jobs,
  page,
  setPage,
  live,
}: {
  jobs: ReturnType<typeof useJobs>;
  page: number;
  setPage: (page: number) => void;
  live: ReturnType<typeof useLiveJobs>;
}) {
  return (
    <>
      {jobs.isPending && <Loader />}
      {jobs.isError && <Alert color="red">{errorMessage(jobs.error)}</Alert>}
      {jobs.data?.items.length === 0 && (
        <Card withBorder>
          <Text c="dimmed">
            No jobs here. Apply a dry run from a library page to start processing files.
          </Text>
        </Card>
      )}
      {jobs.data?.items.map((job) => (
        <JobCard key={job.id} job={withLive(job, live)} />
      ))}
      {jobs.data && jobs.data.total > 50 && (
        <Pagination total={Math.ceil(jobs.data.total / 50)} value={page} onChange={setPage} />
      )}
    </>
  );
}

const ACTIONS: Record<UpcomingItem['action'], string> = {
  encode: 'Re-encode',
  remux: 'Change tracks',
  quarantine: 'Quarantine (wrong language)',
  delete: 'Delete (wrong language)',
};

const WHY: Record<UpcomingWhy, { label: string; color: string; about: string }> = {
  next: {
    label: 'Next',
    color: 'teal',
    about: 'Queued automatically as workers free up, in this order.',
  },
  test_run: {
    label: 'Waiting for a test run',
    color: 'yellow',
    about: 'Re-encodes in this library start once a test run of its profile is approved.',
  },
  not_automatic: {
    label: 'Not automatic',
    color: 'gray',
    about: "The library isn't set to Automatic: apply its dry run to queue these.",
  },
};

function UpcomingList() {
  const [why, setWhy] = useState<UpcomingWhy | null>(null);
  const [page, setPage] = useState(1);
  const upcoming = useUpcoming(why, page);
  const counts = upcoming.data?.counts;
  return (
    <>
      <Text size="sm" c="dimmed">
        Files that still need work but aren&apos;t queued yet. Automatic libraries keep only a few
        jobs waiting (enough to keep every worker busy), and add the next ones as jobs finish.
      </Text>
      <Group gap="xs">
        {([null, 'next', 'test_run', 'not_automatic'] as const).map((w) => (
          <Button
            key={w ?? 'all'}
            size="xs"
            variant={why === w ? 'filled' : 'default'}
            onClick={() => {
              setWhy(w);
              setPage(1);
            }}
          >
            {w === null ? 'All' : WHY[w].label}
            {w !== null && counts ? ` (${counts[w]})` : ''}
          </Button>
        ))}
      </Group>
      {upcoming.isPending && <Loader />}
      {upcoming.isError && <Alert color="red">{errorMessage(upcoming.error)}</Alert>}
      {upcoming.data && (
        <Text size="sm">
          {upcoming.data.total.toLocaleString()} files
          {upcoming.data.saved > 0 && `, saving about ${formatBytes(upcoming.data.saved)}`}.
          {why && ` ${WHY[why].about}`}
        </Text>
      )}
      {upcoming.data?.items.length === 0 && (
        <Card withBorder>
          <Text c="dimmed">Nothing is waiting.</Text>
        </Card>
      )}
      {upcoming.data?.items.map((item) => (
        <Card key={item.file_id} withBorder padding="sm">
          <Group justify="space-between" wrap="nowrap" align="flex-start">
            <Stack gap={2} style={{ minWidth: 0 }}>
              <Text fw={500} style={{ wordBreak: 'break-word' }}>
                {item.relative_path}
              </Text>
              <Text size="xs" c="dimmed">
                {item.library_name} · {ACTIONS[item.action]}
                {item.saved !== null &&
                  item.saved > 0 &&
                  ` · saves about ${formatBytes(item.saved)}`}
              </Text>
            </Stack>
            <Badge color={WHY[item.why].color} variant="light" style={{ flexShrink: 0 }}>
              {WHY[item.why].label}
            </Badge>
          </Group>
        </Card>
      ))}
      {upcoming.data && upcoming.data.total > 50 && (
        <Pagination total={Math.ceil(upcoming.data.total / 50)} value={page} onChange={setPage} />
      )}
    </>
  );
}

function JobCard({ job }: { job: Job }) {
  const cancel = useCancelJob();
  // The card's name ("NVIDIA GeForce RTX 3060") rather than its id.
  const device = useDeviceName()(job.device);
  const retry = useRetryJob();
  const status = STATUS[job.status];
  const saved =
    job.bytes_before !== null && job.bytes_after !== null
      ? job.bytes_before - job.bytes_after
      : null;
  return (
    <Card withBorder>
      <Stack gap="xs">
        <Group justify="space-between" wrap="nowrap" align="flex-start">
          <Stack gap={2} style={{ minWidth: 0 }}>
            <Text fw={500} style={{ wordBreak: 'break-word' }}>
              {job.file}
            </Text>
            <Text size="xs" c="dimmed">
              {job.library_name ?? 'Test film'} · #{job.id} · requested by {job.requested_by}{' '}
              {new Date(job.created_at).toLocaleString()}
            </Text>
          </Stack>
          <Badge color={status.color}>{status.label}</Badge>
        </Group>
        {isActive(job) && (
          <Stack gap={2}>
            <Progress value={job.progress * 100} animated={job.status !== 'queued'} />
            {job.status !== 'queued' && (
              <Text size="xs" c="dimmed">
                {Math.round(job.progress * 100)}%{job.type !== 'remux' && device && ` · ${device}`}
                {job.decoder && ` · ${DECODER[job.decoder]}`}
                {job.fps !== null && ` · ${job.fps.toFixed(0)} fps`}
                {job.speed !== null && ` · ${job.speed.toFixed(1)}× real time`}
                {job.eta_seconds !== null && ` · ${formatTimeLeft(job.eta_seconds)} left`}
              </Text>
            )}
          </Stack>
        )}
        {job.details.length > 0 && (
          <List size="sm">
            {job.details.map((d) => (
              <List.Item key={d}>{d}</List.Item>
            ))}
          </List>
        )}
        {job.status === 'done' && job.outcome === 'no_gain' && (
          <Alert color="gray" title="No gain: the original was kept">
            <Text size="sm">
              The re-encoded file ({formatBytes(job.bytes_after)}) wasn't small enough compared with
              the original ({formatBytes(job.bytes_before)}). ReelHaven won't try this profile on
              this file again.
            </Text>
          </Alert>
        )}
        {job.status === 'done' && job.outcome !== 'no_gain' && saved !== null && (
          <Text size="sm" c="teal">
            Saved {formatBytes(saved)} ({formatBytes(job.bytes_before)} →{' '}
            {formatBytes(job.bytes_after)})
            {job.process_seconds !== null && ` in ${job.process_seconds.toFixed(0)}s`}
            {job.type === 'encode' && device && ` on ${device}`}
            {job.decoder && ` (${DECODER[job.decoder].replace('Decoded', 'decoded')})`}. The
            original is in the recycle bin.
          </Text>
        )}
        {job.status === 'failed' && (
          <Alert color="red" title="The original file was not changed">
            <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>
              {job.error}
            </Text>
          </Alert>
        )}
        {(cancel.isError || retry.isError) && (
          <Text size="sm" c="red">
            {errorMessage(cancel.error ?? retry.error)}
          </Text>
        )}
        <Group gap="xs">
          {isActive(job) && (
            <Button
              size="xs"
              variant="default"
              loading={cancel.isPending}
              onClick={() => cancel.mutate(job.id)}
            >
              Cancel
            </Button>
          )}
          {(job.status === 'failed' || job.status === 'cancelled') &&
            job.media_file_id !== null &&
            job.type !== 'test' &&
            job.type !== 'tune' && (
              <Button
                size="xs"
                variant="light"
                loading={retry.isPending}
                onClick={() => retry.mutate(job.id)}
              >
                Try again
              </Button>
            )}
        </Group>
      </Stack>
    </Card>
  );
}
