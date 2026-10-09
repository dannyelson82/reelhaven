import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Image,
  Loader,
  Progress,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Text,
  Title,
  UnstyledButton,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { IconCheck, IconMaximize, IconPlayerPlay } from '@tabler/icons-react';
import { useState } from 'react';
import { errorMessage } from '../api/client';
import { useDeviceName } from '../api/devices';
import type { Job } from '../api/jobs';
import { useLibraryProfile } from '../api/profiles';
import {
  MAX_SAMPLES,
  type TestRun,
  type TestSample,
  clipsOf,
  frameUrl,
  isUpNext,
  useApproveTestRun,
  useStartTestRun,
  useTestRun,
} from '../api/testRun';
import { useLiveJobs } from '../api/live';
import { CompareViewer } from './CompareViewer';
import { formatBytes, formatDuration, formatTimeLeft } from '../format';

const RATING_COLOR: Record<string, string> = {
  Indistinguishable: 'teal',
  'Very good': 'green',
  Good: 'yellow',
  'Visible loss': 'red',
  Unknown: 'gray',
};

const plural = (n: number) => (n === 1 ? 'file' : 'files');

export function TestRunPanel({ libraryId }: { libraryId: number }) {
  const profile = useLibraryProfile(libraryId);
  const state = useTestRun(libraryId);
  const start = useStartTestRun(libraryId);
  const [chosen, setChosen] = useState<number | null>(null);

  if (profile.isPending || state.isPending) return <Loader />;
  if (profile.data?.profile_id === null) {
    return (
      <Alert color="blue">
        Choose a compression profile for this library first (at the top of the page). Libraries
        without a profile only get language changes, which need no test run.
      </Alert>
    );
  }
  const current = state.data?.run ?? null;
  const samples = chosen ?? state.data?.samples ?? 1;
  return (
    <Stack>
      <Card withBorder>
        <Stack gap="xs">
          <Text size="sm">
            A test run re-encodes a few files with this library's profile, measures the quality and
            shows still frames side by side. It picks the largest files that would be re-encoded,
            mixing resolutions, HDR and titles where it can. <b>Originals are never touched.</b>{' '}
            Re-encoding the whole library unlocks once you approve a test run with the current
            profile.
          </Text>
          <Group align="end">
            <Stack gap={4}>
              <Text size="sm" fw={500}>
                Files to test
              </Text>
              <SegmentedControl
                aria-label="Files to test"
                value={String(samples)}
                onChange={(value) => setChosen(Number(value))}
                data={Array.from({ length: MAX_SAMPLES }, (_, i) => String(i + 1))}
              />
            </Stack>
            <Button
              leftSection={<IconPlayerPlay size={16} />}
              loading={start.isPending}
              disabled={current?.status === 'running'}
              onClick={() => start.mutate(samples)}
            >
              {current ? 'Start a new test run' : 'Start test run'}
            </Button>
          </Group>
          {start.isError && <Alert color="red">{errorMessage(start.error)}</Alert>}
        </Stack>
      </Card>
      {current && <TestRunView libraryId={libraryId} run={current} />}
    </Stack>
  );
}

function TestRunView({ libraryId, run }: { libraryId: number; run: TestRun }) {
  const approve = useApproveTestRun(libraryId);
  const live = useLiveJobs();
  const done = run.samples.filter((s) => s.status === 'done').length;
  const failed = run.samples.filter((s) => s.status === 'failed').length;
  return (
    <Stack>
      {run.status === 'running' && (
        <Text size="sm">
          Testing {run.samples.length} {plural(run.samples.length)}: {done} done
          {failed > 0 && `, ${failed} failed`}.
        </Text>
      )}
      {run.status === 'failed' && (
        <Alert color="red" title="The test run failed">
          {failed} of {run.samples.length} {plural(run.samples.length)} could not be test-encoded,
          so this run can't be approved. See the details below, then start a new test run.
        </Alert>
      )}
      {run.status !== 'running' && !run.profile_is_current && (
        <Alert color="yellow">
          The profile changed since this test run. Start a new one to approve it.
        </Alert>
      )}
      {run.samples.length > 1 && done > 1 && <Summary samples={run.samples} />}
      {run.samples.map((sample) => (
        <SampleView
          key={sample.id}
          sample={sample}
          liveJob={live?.active.find((j) => j.id === sample.job_id)}
          upNext={isUpNext(sample, run.samples)}
        />
      ))}
      {run.status === 'approved' && (
        <Alert color="teal" icon={<IconCheck />}>
          Approved by {run.approved_by} on{' '}
          {run.approved_at && new Date(run.approved_at).toLocaleString()}. Re-encoding this library
          is unlocked.
        </Alert>
      )}
      {run.status === 'done' && (
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

/** Totals over the finished samples, and the weakest quality among them. */
function Summary({ samples }: { samples: TestSample[] }) {
  const results = samples.flatMap((s) => (s.result ? [s.result] : []));
  const before = results.reduce((sum, r) => sum + r.bytes_before, 0);
  const after = results.reduce((sum, r) => sum + r.bytes_after, 0);
  const order = Object.keys(RATING_COLOR);
  const worst = results
    .map((r) => r.rating)
    .reduce((a, b) => (order.indexOf(b) > order.indexOf(a) ? b : a));
  return (
    <Card withBorder>
      <SimpleGrid cols={{ base: 2, sm: 3 }}>
        <Fact label="All tested files" value={`${formatBytes(before)} → ${formatBytes(after)}`} />
        <Fact
          label="Saved overall"
          value={before ? `${(100 * (1 - after / before)).toFixed(1)}%` : '?'}
        />
        <Fact label="Weakest quality" value={worst} color={RATING_COLOR[worst]} />
      </SimpleGrid>
    </Card>
  );
}

function SampleView({
  sample,
  liveJob,
  upNext,
}: {
  sample: TestSample;
  liveJob?: Job;
  upNext: boolean;
}) {
  const deviceName = useDeviceName();
  if (sample.status === 'running') {
    const progress = liveJob?.progress ?? sample.progress;
    const fps = liveJob ? liveJob.fps : sample.fps;
    const eta = liveJob?.eta_seconds ?? null;
    return (
      <Card withBorder>
        <Stack gap="xs">
          <Text size="sm">
            Test-encoding <b>{sample.file}</b>…{' '}
            {upNext
              ? 'up next, once the file before it is done'
              : (liveJob?.status ?? sample.job_status) === 'queued' && 'waiting for a free encoder'}
          </Text>
          <Progress value={progress * 100} animated />
          <Text size="xs" c="dimmed">
            {Math.round(progress * 100)}%{fps !== null && ` · ${fps.toFixed(0)} fps`}
            {eta !== null && ` · ${formatTimeLeft(eta)} left`}
          </Text>
        </Stack>
      </Card>
    );
  }
  if (sample.status === 'failed' || !sample.result) {
    return (
      <Alert color="red" title={`${sample.file} failed`}>
        <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>
          {sample.error}
        </Text>
      </Alert>
    );
  }
  const r = sample.result;
  const enough = r.savings_percent !== null && r.savings_percent >= r.min_savings_percent;
  return (
    <Card withBorder>
      <Stack gap="sm">
        <Group justify="space-between">
          <Title order={4}>{sample.file}</Title>
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
          Encoded on {deviceName(r.device)}
          {r.fps !== null && ` at ${r.fps.toFixed(0)} fps`} in {formatDuration(r.seconds)}.
        </Text>
        {!enough && (
          <Alert color="orange">
            This saves less than the profile's {r.min_savings_percent}% minimum, so a real encode of
            this file would keep the original. Consider a smaller profile.
          </Alert>
        )}
        {r.frame_times.length > 0 && (
          <Stills
            sampleId={sample.id}
            file={sample.file}
            times={r.frame_times}
            clip={r.clip}
            hdr={r.hdr !== null && r.hdr !== 'sdr'}
          />
        )}
      </Stack>
    </Card>
  );
}

function Stills({
  sampleId,
  file,
  times,
  clip,
  hdr,
}: {
  sampleId: number;
  file: string;
  times: number[];
  clip?: { start: number } | null;
  hdr: boolean;
}) {
  const [index, setIndex] = useState(0);
  const [open, setOpen] = useState(false);
  const shown = Math.min(index, times.length - 1);
  return (
    <Stack gap="xs">
      <Group justify="space-between">
        {times.length > 1 ? (
          <SegmentedControl
            size="xs"
            value={String(shown)}
            onChange={(value) => setIndex(Number(value))}
            data={times.map((at, i) => ({ value: String(i), label: formatDuration(at) }))}
            aria-label="Moment"
          />
        ) : (
          <Text size="sm">At {formatDuration(times[0])}</Text>
        )}
        <Button
          size="xs"
          variant="light"
          leftSection={<IconMaximize size={14} />}
          onClick={() => setOpen(true)}
        >
          {clip ? 'Compare full screen, stills and video' : 'Compare full screen'}
        </Button>
      </Group>
      <SimpleGrid cols={{ base: 1, md: 2 }}>
        {(['source', 'encoded'] as const).map((which) => (
          <Stack key={which} gap={4}>
            <Text size="xs" c="dimmed">
              {which === 'source' ? 'Original' : 'Re-encoded'}
            </Text>
            <UnstyledButton onClick={() => setOpen(true)}>
              <Image
                src={frameUrl(sampleId, shown, which)}
                alt={`${which === 'source' ? 'Original' : 'Re-encoded'} at ${formatDuration(times[shown])}`}
                radius="sm"
              />
            </UnstyledButton>
          </Stack>
        ))}
      </SimpleGrid>
      <Text size="xs" c="dimmed">
        Click a still to compare it full screen, zoomed in.
        {hdr &&
          ' HDR stills are converted to normal colours for the browser; judge HDR colours on your TV.'}
      </Text>
      {open && (
        <CompareViewer
          opened
          onClose={() => setOpen(false)}
          title={file}
          start={shown}
          clip={clipsOf(sampleId, clip)}
          stills={times.map((at, i) => ({
            at,
            source: frameUrl(sampleId, i, 'source'),
            encoded: frameUrl(sampleId, i, 'encoded'),
          }))}
          note={hdr ? 'HDR is shown converted to normal colours.' : undefined}
        />
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
