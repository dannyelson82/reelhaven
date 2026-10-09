// Find my sweet spot (ADR-0031): encode one scene at three sizes, compare, dial in, keep.
import {
  Alert,
  Anchor,
  Badge,
  Button,
  Card,
  Group,
  Loader,
  Modal,
  Progress,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import { notifications } from '@mantine/notifications';
import { IconSearch } from '@tabler/icons-react';
import { useState } from 'react';
import { Link, useSearchParams } from 'react-router';
import { errorMessage } from '../api/client';
import { useDeviceName } from '../api/devices';
import { useLibraries } from '../api/libraries';
import {
  CODEC_LABELS,
  type ProfileSettings,
  describeAudio,
  useProfiles,
  useSaveProfile,
} from '../api/profiles';
import {
  type TuneSession,
  type TuneStep,
  nextQualities,
  tuneClipUrl,
  tuneFrameUrl,
  useAddTuneStep,
  useDeleteTune,
  useStartTune,
  useTuneSession,
  useTuneSessions,
} from '../api/tune';
import { CompareViewer } from '../components/CompareViewer';
import { FileChoices } from '../components/MimicModal';
import { formatBytes, formatDuration } from '../format';

const RATING_COLOR: Record<string, string> = {
  Indistinguishable: 'teal',
  'Very good': 'green',
  Good: 'yellow',
  'Visible loss': 'red',
  Unknown: 'gray',
};
// The built-in profiles' levels, so the numbers mean something.
const NAMED: Record<number, string> = { 8: 'High quality', 6: 'Balanced', 4: 'Small' };

const stem = (file: string) => (file.split('/').pop() ?? file).replace(/\.[^.]+$/, '');

/** What every step shares: everything but the quality. */
function describeBase(s: ProfileSettings): string {
  return [
    CODEC_LABELS[s.codec],
    s.ten_bit ? '10-bit' : '8-bit',
    s.max_height ? `max ${s.max_height}p` : 'keep resolution',
    describeAudio(s),
  ].join(' · ');
}

export function SweetSpotPage() {
  const [params, setParams] = useSearchParams();
  const sessionId = params.get('session') ? Number(params.get('session')) : null;
  const open = (id: number | null) => {
    const next = new URLSearchParams(params);
    if (id === null) next.delete('session');
    else next.set('session', String(id));
    setParams(next);
  };
  return (
    <Stack>
      <Title order={2}>Find my sweet spot</Title>
      <Text c="dimmed" maw={720}>
        ReelHaven encodes the same 30-second scene of a file at three sizes, smaller and smaller.
        Compare each with the original, try a version in between, and keep the smallest that still
        looks right as a profile. Your file isn&apos;t touched.
      </Text>
      {sessionId === null ? (
        <Start onStarted={open} />
      ) : (
        <SessionView id={sessionId} onNew={() => open(null)} />
      )}
    </Stack>
  );
}

function Start({ onStarted }: { onStarted: (id: number) => void }) {
  const [params] = useSearchParams();
  const libraries = useLibraries();
  const profiles = useProfiles();
  const sessions = useTuneSessions();
  const start = useStartTune();
  const remove = useDeleteTune();
  const [libraryId, setLibraryId] = useState<number | null>(
    params.get('library') ? Number(params.get('library')) : null,
  );
  const [query, setQuery] = useState('');
  const [debounced] = useDebouncedValue(query, 300);
  const [picked, setPicked] = useState<{ id: number; path: string } | null>(null);
  const fileId = picked?.id ?? null;
  const [profileId, setProfileId] = useState<string | null>(null);
  const library = libraryId ?? libraries.data?.[0]?.id ?? null;
  const balanced = profiles.data?.find((p) => p.builtin && p.name === 'Balanced');
  const base = profiles.data?.find((p) => String(p.id) === profileId) ?? balanced;

  return (
    <Stack>
      <Card withBorder>
        <Stack>
          <Title order={4}>1. Pick a file</Title>
          <Text size="sm" c="dimmed">
            A high-quality file works best: a film you know well, with dark scenes, faces or film
            grain.
          </Text>
          <Group grow>
            <Select
              label="Library"
              data={(libraries.data ?? []).map((l) => ({ value: String(l.id), label: l.name }))}
              value={library === null ? null : String(library)}
              onChange={(v) => setLibraryId(v === null ? null : Number(v))}
              allowDeselect={false}
            />
            <TextInput
              label="Search"
              placeholder="Part of the file name"
              leftSection={<IconSearch size={16} />}
              value={query}
              onChange={(e) => setQuery(e.currentTarget.value)}
            />
          </Group>
          {fileId === null ? (
            library !== null && (
              <FileChoices
                libraryId={library}
                query={debounced}
                onPick={(id, path) => setPicked({ id, path })}
              />
            )
          ) : (
            <Group>
              <Text fw={500} style={{ wordBreak: 'break-word' }}>
                {picked?.path}
              </Text>
              <Anchor component="button" size="sm" onClick={() => setPicked(null)}>
                Pick another
              </Anchor>
            </Group>
          )}
          <Title order={4}>2. Settings to try</Title>
          <Select
            label="Start from profile"
            description="Its format, 10-bit, resolution and audio are used; ReelHaven tries the quality."
            data={(profiles.data ?? []).map((p) => ({ value: String(p.id), label: p.name }))}
            value={base ? String(base.id) : null}
            onChange={setProfileId}
            allowDeselect={false}
          />
          {base && (
            <Text size="sm" c="dimmed">
              {describeBase(base.settings)}
            </Text>
          )}
          {start.isError && <Alert color="red">{errorMessage(start.error)}</Alert>}
          <Group>
            <Button
              disabled={fileId === null || !base}
              loading={start.isPending}
              onClick={() =>
                base &&
                fileId !== null &&
                start.mutate(
                  { file_id: fileId, settings: base.settings },
                  { onSuccess: (s) => s && onStarted(s.id) },
                )
              }
            >
              Encode three versions
            </Button>
          </Group>
        </Stack>
      </Card>
      {(sessions.data ?? []).length > 0 && (
        <Stack gap="xs">
          <Title order={4}>Recent</Title>
          {sessions.data?.map((s) => (
            <Card key={s.id} withBorder padding="sm">
              <Group justify="space-between" wrap="nowrap">
                <Stack gap={0} style={{ minWidth: 0 }}>
                  <Text fw={500} truncate>
                    {s.file}
                  </Text>
                  <Text size="xs" c="dimmed">
                    {s.steps.length} versions · {new Date(s.created_at).toLocaleString()}
                  </Text>
                </Stack>
                <Group gap="xs" wrap="nowrap">
                  <Button size="xs" variant="light" onClick={() => onStarted(s.id)}>
                    Open
                  </Button>
                  <Button
                    size="xs"
                    variant="default"
                    loading={remove.isPending && remove.variables === s.id}
                    onClick={() => remove.mutate(s.id)}
                  >
                    Delete
                  </Button>
                </Group>
              </Group>
            </Card>
          ))}
        </Stack>
      )}
    </Stack>
  );
}

function SessionView({ id, onNew }: { id: number; onNew: () => void }) {
  const session = useTuneSession(id);
  const add = useAddTuneStep(id);
  const [comparing, setComparing] = useState<TuneStep | null>(null);
  const [keeping, setKeeping] = useState<TuneStep | null>(null);

  if (session.isPending) return <Loader />;
  if (session.isError) return <Alert color="red">{errorMessage(session.error)}</Alert>;
  const s = session.data;
  const next = nextQualities(s.steps.map((step) => step.quality));
  const tryButton = (label: string, quality: number) => (
    <Button
      key={label}
      size="xs"
      variant="light"
      loading={add.isPending && add.variables === quality}
      onClick={() => add.mutate(quality)}
    >
      {label}
    </Button>
  );

  return (
    <Stack>
      <Group justify="space-between" align="flex-start">
        <Stack gap={2} style={{ minWidth: 0 }}>
          <Text fw={600} style={{ wordBreak: 'break-word' }}>
            {s.file}
          </Text>
          <Text size="sm" c="dimmed">
            {formatBytes(s.file_bytes)} now · a {s.scene_seconds.toFixed(0)}-second scene from{' '}
            {formatDuration(s.scene_start)} · {describeBase(s.base)}
          </Text>
        </Stack>
        <Button variant="default" onClick={onNew}>
          Start another
        </Button>
      </Group>
      <SimpleGrid cols={{ base: 1, sm: 2, lg: Math.min(4, Math.max(s.steps.length, 1)) }}>
        {s.steps.map((step) => (
          <StepCard
            key={step.id}
            step={step}
            onCompare={() => setComparing(step)}
            onKeep={() => setKeeping(step)}
          />
        ))}
      </SimpleGrid>
      <Card withBorder>
        <Stack gap="xs">
          <Text fw={500}>Try another version</Text>
          <Text size="sm" c="dimmed">
            Found two where one looks right and the next doesn&apos;t? Try the one in between. Half
            steps (6.5) are allowed.
          </Text>
          <Group gap="xs">
            {next.better !== null && tryButton(`Better: ${next.better}`, next.better)}
            {next.between.map(([high, low, mid]) =>
              tryButton(`Between ${high} and ${low}: ${mid}`, mid),
            )}
            {next.smaller !== null && tryButton(`Smaller: ${next.smaller}`, next.smaller)}
          </Group>
          {add.isError && <Alert color="red">{errorMessage(add.error)}</Alert>}
        </Stack>
      </Card>
      {comparing?.result && (
        <CompareViewer
          opened
          onClose={() => setComparing(null)}
          title={`${s.file}: quality ${comparing.quality}`}
          after={`Quality ${comparing.quality}`}
          stills={comparing.result.frame_times.map((at, i) => ({
            at,
            source: tuneFrameUrl(comparing.id, i, 'source'),
            encoded: tuneFrameUrl(comparing.id, i, 'encoded'),
          }))}
          clip={
            comparing.result.clip
              ? {
                  source: tuneClipUrl(comparing.id, 'source'),
                  encoded: tuneClipUrl(comparing.id, 'encoded'),
                  start: s.scene_start + comparing.result.clip.start,
                }
              : null
          }
          note={
            comparing.result.hdr && comparing.result.hdr !== 'sdr'
              ? 'HDR is shown converted to normal colours.'
              : undefined
          }
        />
      )}
      {keeping && <KeepModal session={s} step={keeping} onClose={() => setKeeping(null)} />}
    </Stack>
  );
}

function StepCard({
  step,
  onCompare,
  onKeep,
}: {
  step: TuneStep;
  onCompare: () => void;
  onKeep: () => void;
}) {
  const deviceName = useDeviceName();
  const r = step.result;
  return (
    <Card withBorder>
      <Stack gap="xs">
        <Group justify="space-between">
          <Text fw={700}>
            Quality {step.quality}
            {NAMED[step.quality] && (
              <Text span size="sm" c="dimmed" fw={400}>
                {' '}
                ({NAMED[step.quality]})
              </Text>
            )}
          </Text>
          {r && <Badge color={RATING_COLOR[r.rating] ?? 'gray'}>{r.rating}</Badge>}
        </Group>
        {step.status === 'queued' && (
          <Text size="sm" c="dimmed">
            Waiting for a free graphics card…
          </Text>
        )}
        {step.status === 'running' && (
          <Stack gap={2}>
            <Progress value={step.progress * 100} animated />
            <Text size="xs" c="dimmed">
              {Math.round(step.progress * 100)}%
              {step.fps !== null && ` · ${step.fps.toFixed(0)} fps`}
            </Text>
          </Stack>
        )}
        {step.status === 'failed' && (
          <Alert color="red" title="Couldn't encode this one">
            {step.error}
          </Alert>
        )}
        {r && (
          <>
            <Text size="lg" fw={700}>
              ≈ {formatBytes(r.bytes_after)}
            </Text>
            <Text
              size="sm"
              c={r.savings_percent !== null && r.savings_percent > 0 ? 'teal' : 'dimmed'}
            >
              {r.savings_percent !== null && r.savings_percent > 0
                ? `Saves about ${formatBytes(r.bytes_before - r.bytes_after)} (${r.savings_percent.toFixed(0)}%)`
                : 'No smaller than the original'}
            </Text>
            <Text size="xs" c="dimmed">
              {[r.xpsnr !== null && `XPSNR ${r.xpsnr} dB`, r.ssim !== null && `SSIM ${r.ssim}`]
                .filter(Boolean)
                .join(' · ')}
              {` · ${deviceName(r.device)}`}
            </Text>
            <Group gap="xs">
              <Button size="xs" variant="light" onClick={onCompare}>
                Compare
              </Button>
              <Button size="xs" onClick={onKeep}>
                Keep this
              </Button>
            </Group>
          </>
        )}
      </Stack>
    </Card>
  );
}

function KeepModal({
  session,
  step,
  onClose,
}: {
  session: TuneSession;
  step: TuneStep;
  onClose: () => void;
}) {
  const [params] = useSearchParams();
  const save = useSaveProfile();
  const [name, setName] = useState(
    `Sweet spot ${step.quality} (${stem(session.file)})`.slice(0, 100),
  );
  const [saved, setSaved] = useState<number | null>(null);
  const wizardLibrary = params.get('from') === 'wizard' ? params.get('library') : null;
  return (
    <Modal opened onClose={onClose} title="Keep this as a profile">
      {saved === null ? (
        <Stack>
          <Text size="sm">
            Saves {describeBase(session.base)} at quality {step.quality} as a profile you can choose
            for any library.
          </Text>
          <TextInput label="Name" value={name} onChange={(e) => setName(e.currentTarget.value)} />
          {save.isError && <Alert color="red">{errorMessage(save.error)}</Alert>}
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button
              disabled={!name.trim()}
              loading={save.isPending}
              onClick={() =>
                save.mutate(
                  { name: name.trim(), settings: { ...session.base, quality: step.quality } },
                  {
                    onSuccess: (profile) => {
                      notifications.show({ message: `Profile "${profile.name}" saved.` });
                      setSaved(profile.id);
                    },
                  },
                )
              }
            >
              Save profile
            </Button>
          </Group>
        </Stack>
      ) : (
        <Stack>
          <Text size="sm">
            Saved. Choose it for a library on the library&apos;s page, and check it with a test run
            first.
          </Text>
          <Group justify="flex-end">
            {wizardLibrary !== null ? (
              <Button
                component={Link}
                to={`/wizard?library=${wizardLibrary}&step=quality&choice=${saved}`}
              >
                Back to the wizard
              </Button>
            ) : (
              <Button component={Link} to="/profiles">
                Go to Profiles
              </Button>
            )}
          </Group>
        </Stack>
      )}
    </Modal>
  );
}
