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
import {
  type Job,
  type JobFilter,
  isActive,
  useCancelJob,
  useJobs,
  useRetryJob,
} from '../api/jobs';
import { formatBytes } from '../format';

const STATUS: Record<Job['status'], { label: string; color: string }> = {
  queued: { label: 'Waiting', color: 'gray' },
  running: { label: 'Remuxing', color: 'blue' },
  verifying: { label: 'Checking', color: 'cyan' },
  done: { label: 'Done', color: 'teal' },
  failed: { label: 'Failed', color: 'red' },
  cancelled: { label: 'Cancelled', color: 'gray' },
};

export function JobsPage() {
  const [filter, setFilter] = useState<JobFilter>('all');
  const [page, setPage] = useState(1);
  const jobs = useJobs(filter, page);
  const counts = jobs.data?.counts ?? {};
  const active = (counts.queued ?? 0) + (counts.running ?? 0) + (counts.verifying ?? 0);
  const failed = (counts.failed ?? 0) + (counts.cancelled ?? 0);

  return (
    <Stack maw={960}>
      <Title order={2}>Jobs</Title>
      <SegmentedControl
        value={filter}
        onChange={(v) => {
          setFilter(v as JobFilter);
          setPage(1);
        }}
        data={[
          { value: 'all', label: 'All' },
          { value: 'active', label: `In progress (${active})` },
          { value: 'failed', label: `Failed (${failed})` },
          { value: 'done', label: `Done (${counts.done ?? 0})` },
        ]}
        w="fit-content"
      />
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
        <JobCard key={job.id} job={job} />
      ))}
      {jobs.data && jobs.data.total > 50 && (
        <Pagination total={Math.ceil(jobs.data.total / 50)} value={page} onChange={setPage} />
      )}
    </Stack>
  );
}

function JobCard({ job }: { job: Job }) {
  const cancel = useCancelJob();
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
              {job.library_name} · #{job.id} · requested by {job.requested_by}{' '}
              {new Date(job.created_at).toLocaleString()}
            </Text>
          </Stack>
          <Badge color={status.color}>{status.label}</Badge>
        </Group>
        {isActive(job) && (
          <Progress value={job.progress * 100} animated={job.status !== 'queued'} />
        )}
        {job.details.length > 0 && (
          <List size="sm">
            {job.details.map((d) => (
              <List.Item key={d}>{d}</List.Item>
            ))}
          </List>
        )}
        {job.status === 'done' && saved !== null && (
          <Text size="sm" c="teal">
            Saved {formatBytes(saved)} ({formatBytes(job.bytes_before)} →{' '}
            {formatBytes(job.bytes_after)})
            {job.process_seconds !== null && ` in ${job.process_seconds.toFixed(0)}s`}. The original
            is in the recycle bin.
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
            job.media_file_id !== null && (
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
