// The wizard's last steps (ADR-0026): try it on a few files, go automatic, done.
import {
  Alert,
  Anchor,
  Badge,
  Button,
  Card,
  Checkbox,
  Group,
  Image,
  List,
  Loader,
  Progress,
  SimpleGrid,
  Stack,
  Text,
  ThemeIcon,
  UnstyledButton,
} from '@mantine/core';
import { IconCheck, IconMaximize } from '@tabler/icons-react';
import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router';
import { errorMessage } from '../api/client';
import { KeepOriginalsControl, OriginalsNote } from '../components/KeepOriginals';
import {
  KEEP_DAYS,
  type KeepDays,
  useRecycleSettings,
  useSaveRecycleSettings,
} from '../api/recycleSettings';
import { useDevices } from '../api/devices';
import { useDryRun } from '../api/dryrun';
import { useScanStatus } from '../api/files';
import { type WatchMode, useLibraries, useSetWatchMode } from '../api/libraries';
import { useLibraryProfile, useProfiles } from '../api/profiles';
import {
  type TestSample,
  clipsOf,
  frameUrl,
  isUpNext,
  useApproveTestRun,
  useStartTestRun,
  useTestRun,
} from '../api/testRun';
import { useLiveJobs } from '../api/live';
import { CompareViewer } from '../components/CompareViewer';
import { ScanProgress } from '../components/ScanProgress';
import { formatBytes, formatTimeLeft } from '../format';
import { canEncode } from './choices';
import type { StepProps } from './LibrarySteps';

const RATING_COLOR: Record<string, string> = {
  Indistinguishable: 'teal',
  'Very good': 'green',
  Good: 'yellow',
  'Visible loss': 'red',
  Unknown: 'gray',
};
const SAMPLES = 2;

function NavButtons({ onBack, next }: { onBack?: () => void; next: React.ReactNode }) {
  return (
    <Group justify="space-between" mt="md">
      {onBack ? (
        <Button variant="default" onClick={onBack}>
          Back
        </Button>
      ) : (
        <span />
      )}
      {next}
    </Group>
  );
}

function SampleResult({ sample, upNext }: { sample: TestSample; upNext: boolean }) {
  const [open, setOpen] = useState(false);
  const live = useLiveJobs();
  const job = live?.active.find((j) => j.id === sample.job_id);
  if (sample.status === 'running') {
    const progress = job?.progress ?? sample.progress;
    return (
      <Card withBorder>
        <Stack gap={4}>
          <Text size="sm" fw={500} truncate>
            {sample.file}
          </Text>
          <Progress value={progress * 100} animated />
          <Text size="xs" c="dimmed">
            {upNext
              ? 'Up next, once the file before it is done'
              : sample.job_status === 'queued' && !job
                ? 'Waiting for a free encoder…'
                : `${Math.round(progress * 100)}%`}
            {job?.eta_seconds != null && ` · ${formatTimeLeft(job.eta_seconds)} left`}
          </Text>
        </Stack>
      </Card>
    );
  }
  if (sample.status === 'failed' || !sample.result) {
    return (
      <Alert color="red" title={`${sample.file} couldn't be test-encoded`}>
        {sample.error}
      </Alert>
    );
  }
  const r = sample.result;
  return (
    <Card withBorder>
      <Stack gap="xs">
        <Group justify="space-between" wrap="nowrap">
          <Text size="sm" fw={500} truncate>
            {sample.file}
          </Text>
          <Badge color={RATING_COLOR[r.rating] ?? 'gray'}>{r.rating}</Badge>
        </Group>
        <Text size="sm">
          {formatBytes(r.bytes_before)} → {formatBytes(r.bytes_after)}
          {r.savings_percent !== null && ` (${r.savings_percent}% smaller)`}
        </Text>
        {r.frame_times.length > 0 && (
          <>
            <UnstyledButton onClick={() => setOpen(true)}>
              <SimpleGrid cols={2} spacing="xs">
                <Stack gap={2}>
                  <Text size="xs" c="dimmed">
                    Original
                  </Text>
                  <Image src={frameUrl(sample.id, 0, 'source')} alt="Original" radius="sm" />
                </Stack>
                <Stack gap={2}>
                  <Text size="xs" c="dimmed">
                    Smaller
                  </Text>
                  <Image
                    src={frameUrl(sample.id, 0, 'encoded')}
                    alt="Smaller version"
                    radius="sm"
                  />
                </Stack>
              </SimpleGrid>
            </UnstyledButton>
            <Button
              size="xs"
              variant="light"
              leftSection={<IconMaximize size={14} />}
              onClick={() => setOpen(true)}
            >
              Look closer, full screen
            </Button>
            {open && (
              <CompareViewer
                opened
                onClose={() => setOpen(false)}
                title={sample.file}
                after="Smaller"
                clip={clipsOf(sample.id, r.clip)}
                stills={r.frame_times.map((at, i) => ({
                  at,
                  source: frameUrl(sample.id, i, 'source'),
                  encoded: frameUrl(sample.id, i, 'encoded'),
                }))}
                note={
                  r.hdr && r.hdr !== 'sdr' ? 'HDR is shown converted to normal colours.' : undefined
                }
              />
            )}
          </>
        )}
      </Stack>
    </Card>
  );
}

export function TryStep({ libraryId, onNext, onBack }: StepProps) {
  const id = libraryId ?? 0;
  const state = useTestRun(id);
  const start = useStartTestRun(id);
  const approve = useApproveTestRun(id);
  const devices = useDevices();
  const libraryProfile = useLibraryProfile(id);
  const profiles = useProfiles();
  const started = useRef(false);
  const run = state.data?.run ?? null;
  const fresh = run !== null && run.profile_is_current;

  useEffect(() => {
    // Start a test run on arrival, unless one with this profile already exists.
    if (!started.current && state.data && !fresh) {
      started.current = true;
      start.mutate(SAMPLES);
    }
  }, [state.data, fresh, start]);

  const settings = profiles.data?.find((p) => p.id === libraryProfile.data?.profile_id)?.settings;
  const stuck =
    settings && devices.data?.detected_at
      ? !canEncode(devices.data.devices, settings.codec, settings.ten_bit)
      : false;

  if (!state.data) return <Loader />;
  return (
    <Stack>
      <Text>
        Before anything changes in your library, ReelHaven tries your choice on {SAMPLES} of your
        files. Your originals aren't touched. Compare the pictures: if you can't tell them apart,
        it's good.
      </Text>
      {stuck && (
        <Alert color="yellow" title="Nothing can encode this yet">
          No graphics card is set up for this format, and CPU encoding is off. Turn on{' '}
          <b>Allow CPU encoding</b> on the{' '}
          <Anchor component={Link} to="/settings/hardware">
            Hardware
          </Anchor>{' '}
          page (slower), or give ReelHaven your GPU.
        </Alert>
      )}
      {start.isError && <Alert color="red">{errorMessage(start.error)}</Alert>}
      {(!fresh || !run) && <Loader size="sm" />}
      {fresh && run && (
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          {run.samples.map((sample) => (
            <SampleResult key={sample.id} sample={sample} upNext={isUpNext(sample, run.samples)} />
          ))}
        </SimpleGrid>
      )}
      {fresh && run?.status === 'failed' && (
        <Group>
          <Button variant="light" onClick={() => start.mutate(SAMPLES)} loading={start.isPending}>
            Try again
          </Button>
        </Group>
      )}
      {approve.isError && <Alert color="red">{errorMessage(approve.error)}</Alert>}
      <NavButtons
        onBack={onBack}
        next={
          <Group gap="xs">
            {onBack && fresh && run?.status !== 'running' && (
              <Button variant="default" onClick={onBack}>
                Try another setting
              </Button>
            )}
            <Button
              color="teal"
              leftSection={<IconCheck size={16} />}
              disabled={!fresh || (run?.status !== 'done' && run?.status !== 'approved')}
              loading={approve.isPending}
              onClick={() => {
                if (run?.status === 'approved') onNext();
                else if (run) approve.mutate(run.id, { onSuccess: () => onNext() });
              }}
            >
              Looks good
            </Button>
          </Group>
        }
      />
    </Stack>
  );
}

export function AutomaticStep({ libraryId, onNext, onBack }: StepProps) {
  const id = libraryId ?? 0;
  const [params, setParams] = useSearchParams();
  const libraries = useLibraries();
  const library = libraries.data?.find((l) => l.id === id);
  const dry = useDryRun(id, 'changes', 1, true);
  const set = useSetWatchMode();
  const mode = (params.get('mode') as WatchMode | null) ?? 'automatic';
  const choose = (value: WatchMode) => {
    const next = new URLSearchParams(params);
    next.set('mode', value);
    setParams(next, { replace: true });
  };
  const work = dry.data ? dry.data.encode + dry.data.remux : null;
  const scan = useScanStatus(id, true).data;

  return (
    <Stack>
      <Text>
        Last step: should ReelHaven look after {library?.name ?? 'this library'} by itself?
      </Text>
      {scan?.state === 'scanning' ? (
        <Alert color="blue" title="Still reading your files">
          <Stack gap="xs">
            <ScanProgress status={scan} />
            <Text size="sm">
              Nothing in the library changes until ReelHaven has finished reading it and looked up
              each title's original language. Your choice applies from then on.
            </Text>
          </Stack>
        </Alert>
      ) : (
        dry.data && (
          <Alert color="blue">
            {work === 0
              ? 'Nothing needs changing right now; new files will be handled as they arrive.'
              : `${work} ${work === 1 ? 'file needs' : 'files need'} work, saving about ${formatBytes(dry.data.saved_bytes)}.`}
          </Alert>
        )
      )}
      <SimpleGrid cols={{ base: 1, sm: 2 }}>
        {(
          [
            {
              value: 'automatic',
              title: 'Yes, automatically (recommended)',
              text: 'Works through every file, a few at a time, and handles new files as they arrive.',
            },
            {
              value: 'watch',
              title: 'Not yet, just watch',
              text: 'New files are found and planned, but nothing changes until you apply it yourself.',
            },
          ] as const
        ).map((option) => (
          <Card
            key={option.value}
            withBorder
            component="button"
            type="button"
            aria-pressed={mode === option.value}
            onClick={() => choose(option.value)}
            style={{
              textAlign: 'left',
              cursor: 'pointer',
              borderColor: mode === option.value ? 'var(--mantine-color-teal-6)' : undefined,
              borderWidth: mode === option.value ? 2 : undefined,
            }}
          >
            <Text fw={700}>{option.title}</Text>
            <Text size="sm" c="dimmed">
              {option.text}
            </Text>
          </Card>
        ))}
      </SimpleGrid>
      <Text size="sm" c="dimmed">
        <OriginalsNote /> You can pause everything at any time from the Jobs page, and change this
        on the library's page.
      </Text>
      {set.isError && <Alert color="red">{errorMessage(set.error)}</Alert>}
      <NavButtons
        onBack={onBack}
        next={
          <Button
            loading={set.isPending}
            onClick={() => set.mutate({ id, watch_mode: mode }, { onSuccess: () => onNext() })}
          >
            {mode === 'automatic' ? 'Start' : 'Finish'}
          </Button>
        }
      />
    </Stack>
  );
}

export function DoneStep({ libraryId }: StepProps) {
  const [params] = useSearchParams();
  const libraries = useLibraries();
  const library = libraries.data?.find((l) => l.id === libraryId);
  const automatic = library?.watch_mode === 'automatic' || params.get('mode') !== 'watch';
  const reading = useScanStatus(libraryId ?? 0, true).data?.state === 'scanning';
  return (
    <Stack align="flex-start">
      <Group>
        <ThemeIcon color="teal" size="lg" radius="xl">
          <IconCheck />
        </ThemeIcon>
        <Text fw={700} size="lg">
          {library?.name ?? 'Your library'} is set up.
        </Text>
      </Group>
      <List size="sm">
        {automatic ? (
          <>
            <List.Item>
              {reading
                ? 'ReelHaven finishes reading the library first, then works through the files, a few at a time.'
                : 'ReelHaven is working through the files now, a few at a time.'}
            </List.Item>
            <List.Item>New files are noticed within minutes and handled the same way.</List.Item>
          </>
        ) : (
          <List.Item>New files are found and planned; apply them from the Dry run tab.</List.Item>
        )}
        <List.Item>
          <OriginalsNote />
        </List.Item>
      </List>
      <Group>
        <Button component={Link} to="/jobs">
          See the progress
        </Button>
        <Button component={Link} to="/wizard" variant="default">
          Set up another library
        </Button>
        <Button component={Link} to="/" variant="subtle">
          Dashboard
        </Button>
      </Group>
    </Stack>
  );
}

/** How long originals are kept (ADR-0028). One setting for the whole server. */
export function SafetyNetStep({ onNext, onBack }: StepProps) {
  const [params, setParams] = useSearchParams();
  const setting = useRecycleSettings();
  const save = useSaveRecycleSettings();
  const [understood, setUnderstood] = useState(false);
  if (!setting.data) return <Loader />;
  const current = setting.data.keep_days;
  const fromUrl = Number(params.get('keep'));
  const keep =
    (KEEP_DAYS as readonly number[]).includes(fromUrl) && params.has('keep')
      ? (fromUrl as KeepDays)
      : current;
  const choose = (days: KeepDays) => {
    const next = new URLSearchParams(params);
    next.set('keep', String(days));
    setParams(next, { replace: true });
    setUnderstood(false);
  };
  return (
    <Stack>
      <Text>
        When ReelHaven replaces a file, it can keep the original in a recycle bin for a while, so
        you can put it back if you don't like the result. How long should originals be kept?
      </Text>
      <KeepOriginalsControl value={keep} onChange={choose} />
      {keep === 0 && current !== 0 && (
        <Checkbox
          label="I understand that replaced files can't be put back"
          checked={understood}
          onChange={(e) => setUnderstood(e.currentTarget.checked)}
        />
      )}
      <Text size="sm" c="dimmed">
        This applies to every library. You can change it any time on the Recycle bin page.
      </Text>
      {save.isError && <Alert color="red">{errorMessage(save.error)}</Alert>}
      <NavButtons
        onBack={onBack}
        next={
          <Button
            disabled={keep === 0 && current !== 0 && !understood}
            loading={save.isPending}
            onClick={() =>
              keep === current
                ? onNext()
                : save.mutate({ keep_days: keep }, { onSuccess: () => onNext() })
            }
          >
            Next
          </Button>
        }
      />
    </Stack>
  );
}
