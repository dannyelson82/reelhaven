// The wizard's choices (ADR-0026): how small vs how good, and what to do with audio.
import {
  Alert,
  Anchor,
  Badge,
  Button,
  Card,
  Collapse,
  Group,
  Loader,
  Select,
  SimpleGrid,
  Stack,
  Text,
  UnstyledButton,
} from '@mantine/core';
import { useState } from 'react';
import { useSearchParams } from 'react-router';
import { errorMessage } from '../api/client';
import {
  type Profile,
  describe,
  describeAudio,
  useMimic,
  type ProfileSettings,
  useProfiles,
  useSaveProfile,
  useSetLibraryProfile,
} from '../api/profiles';
import { useScanStatus } from '../api/files';
import { useRecycleSettings } from '../api/recycleSettings';
import { type Estimate, type EstimateSummary, useEstimate } from '../api/wizard';
import { ScanProgress } from '../components/ScanProgress';
import { formatBytes } from '../format';
import {
  AUDIO_CHOICES,
  defaultAudioChoice,
  hasOwnAudio,
  type AudioChoice,
  PRESETS,
  findProfile,
  profileName,
  withAudio,
} from './choices';
import type { StepProps } from './LibrarySteps';
import { AudioGuide } from '../components/AudioGuide';
import { MimicModal } from '../components/MimicModal';

/** The quality step's "Copy a file I like" choice. */
const MIMIC = 'mimic';

/** What a file's settings would save on the library, inside the Mimic result. */
function MimicSaving({ libraryId, settings }: { libraryId: number; settings: ProfileSettings }) {
  const estimate = useEstimate(libraryId, { [MIMIC]: settings });
  const { ready, scale } = readiness(estimate.data);
  return (
    <Saving
      result={ready ? estimate.data?.results[MIMIC] : undefined}
      libraryBytes={estimate.data?.library_bytes}
      scale={scale}
    />
  );
}

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

function Saving({
  result,
  libraryBytes,
  extra = false,
  scale = 1,
}: {
  result?: EstimateSummary;
  libraryBytes?: number;
  extra?: boolean;
  scale?: number;
}) {
  if (!result) {
    return (
      <Group gap={6}>
        <Loader size="xs" />
        <Text size="sm" c="dimmed">
          Working it out…
        </Text>
      </Group>
    );
  }
  if (result.saved_bytes <= 0) {
    return (
      <Text size="sm" c="dimmed">
        {extra ? 'No extra saving here' : 'Little to save: your files are already efficient'}
      </Text>
    );
  }
  const pct = libraryBytes ? Math.round((100 * result.saved_bytes) / libraryBytes) : null;
  return (
    <Text size="sm" fw={600} c="teal">
      {extra ? 'About ' : 'Saves about '}
      {formatBytes(result.saved_bytes * scale)}
      {extra ? ' more' : ''}
      {pct !== null && !extra && ` (${pct}%)`}
    </Text>
  );
}

/** Files read before estimates are shown while a library is still being read (ADR-0027). */
export const MIN_READ = 200;

function readiness(estimate?: Estimate) {
  const reading = estimate?.reading ?? null;
  const ready =
    estimate !== undefined &&
    (reading === null ||
      (reading.to_probe > 0 && reading.probed >= Math.min(MIN_READ, reading.to_probe)));
  // Savings on the files read so far, scaled to the whole library by size.
  const scale =
    reading && estimate && estimate.library_bytes > 0
      ? Math.max(1, reading.found_bytes / estimate.library_bytes)
      : 1;
  return { reading, ready, scale };
}

function ReadingNote({ libraryId, estimate }: { libraryId: number; estimate?: Estimate }) {
  const { reading, ready } = readiness(estimate);
  const scan = useScanStatus(libraryId, reading !== null);
  if (!reading) return null;
  if (!ready) {
    return (
      <Stack gap="xs">
        <Text size="sm">
          ReelHaven is still reading your files. The estimates appear once the first{' '}
          {Math.min(MIN_READ, reading.to_probe || MIN_READ)} have been read.
        </Text>
        {scan.data?.state === 'scanning' && <ScanProgress status={scan.data} />}
      </Stack>
    );
  }
  return (
    <Text size="sm" c="dimmed">
      Estimated from {reading.probed.toLocaleString()} of {reading.to_probe.toLocaleString()} files
      read so far. ReelHaven keeps reading in the background, and the numbers settle as it goes.
    </Text>
  );
}

function ChoiceCard({
  selected,
  title,
  description,
  onClick,
  children,
}: {
  selected: boolean;
  title: string;
  description: string;
  onClick: () => void;
  children?: React.ReactNode;
}) {
  return (
    <UnstyledButton onClick={onClick} aria-pressed={selected} style={{ height: '100%' }}>
      <Card
        withBorder
        h="100%"
        style={{
          borderColor: selected ? 'var(--mantine-color-teal-6)' : undefined,
          borderWidth: selected ? 2 : undefined,
        }}
      >
        <Stack gap={6}>
          <Group justify="space-between">
            <Text fw={700}>{title}</Text>
            {selected && <Badge color="teal">Chosen</Badge>}
          </Group>
          <Text size="sm" c="dimmed">
            {description}
          </Text>
          {children}
        </Stack>
      </Card>
    </UnstyledButton>
  );
}

export function QualityStep({ libraryId, onNext, onBack }: StepProps) {
  const id = libraryId ?? 0;
  const [params, setParams] = useSearchParams();
  const profiles = useProfiles();
  const setProfile = useSetLibraryProfile(id);
  const save = useSaveProfile();
  const [more, setMore] = useState(false);
  const [picking, setPicking] = useState(false);
  const mimicFile = params.get('mimic');
  const mimic = useMimic(mimicFile ? Number(mimicFile) : null);
  const builtins = Object.fromEntries(
    (profiles.data ?? []).filter((p) => p.builtin).map((p) => [p.name, p]),
  );
  const presets = PRESETS.map((preset) => ({ ...preset, profile: builtins[preset.builtin] }));
  const candidates: Record<string, ProfileSettings> = Object.fromEntries(
    presets.filter((p) => p.profile).map((p) => [String(p.profile.id), p.profile.settings]),
  );
  if (mimic.data) candidates[MIMIC] = mimic.data.report.settings;
  const estimate = useEstimate(id, candidates);
  const { ready, scale } = readiness(estimate.data);
  const balancedId = builtins.Balanced ? String(builtins.Balanced.id) : null;
  const choice = params.get('choice') ?? balancedId;
  const others = (profiles.data ?? []).filter((p) => !presets.some((x) => x.profile?.id === p.id));
  const isPreset = presets.some((p) => String(p.profile?.id) === choice);

  if (!profiles.data) return <Loader />;
  const choose = (value: string, mimicId?: number) => {
    const next = new URLSearchParams(params);
    next.set('choice', value);
    if (mimicId !== undefined) next.set('mimic', String(mimicId));
    setParams(next, { replace: true });
  };
  // The file's settings become a profile (or an identical existing one) on Next.
  const saveMimic = async () => {
    if (!mimic.data) return;
    const { file, report } = mimic.data;
    if (findProfile(profiles.data, report.settings)) return;
    const stem = (file.split('/').pop() ?? file).replace(/\.[^.]+$/, '');
    await save.mutateAsync({
      name: profileName(
        `Like ${stem}`.slice(0, 90),
        'keep',
        profiles.data.map((p) => p.name),
      ),
      settings: report.settings,
      mimic: { file, sources: report.sources, notes: report.notes },
    });
  };

  return (
    <Stack>
      <Text>
        How small should your files get? Each choice shows what it would save on this library; the
        test run in a moment shows the real result.
      </Text>
      <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
        {presets.map((preset) =>
          preset.profile ? (
            <ChoiceCard
              key={preset.key}
              selected={choice === String(preset.profile.id)}
              title={preset.title}
              description={preset.description}
              onClick={() => choose(String(preset.profile.id))}
            >
              <Saving
                result={ready ? estimate.data?.results[String(preset.profile.id)] : undefined}
                libraryBytes={estimate.data?.library_bytes}
                scale={scale}
              />
            </ChoiceCard>
          ) : null,
        )}
        <ChoiceCard
          selected={choice === MIMIC}
          title="Copy a file I like"
          description={
            mimic.data
              ? `Like ${mimic.data.file.split('/').pop()}: ${describe(mimic.data.report.settings)}.`
              : 'Pick a file in this library whose size and quality you like; ReelHaven matches it.'
          }
          onClick={() => (mimic.data && choice !== MIMIC ? choose(MIMIC) : setPicking(true))}
        >
          {mimic.data ? (
            <>
              <Saving
                result={ready ? estimate.data?.results[MIMIC] : undefined}
                libraryBytes={estimate.data?.library_bytes}
                scale={scale}
              />
              {choice === MIMIC && (
                <Text size="xs" c="dimmed">
                  Click again to pick another file.
                </Text>
              )}
            </>
          ) : mimic.isFetching ? (
            <Loader size="xs" />
          ) : null}
        </ChoiceCard>
      </SimpleGrid>
      {picking && (
        <MimicModal
          only={id}
          title="Copy a file I like"
          useLabel="Choose this"
          extra={(report) => <MimicSaving libraryId={id} settings={report.settings} />}
          onClose={() => setPicking(false)}
          onUse={(_file, _report, fileId) => {
            setPicking(false);
            choose(MIMIC, fileId);
          }}
        />
      )}
      {estimate.isError && <Alert color="red">{errorMessage(estimate.error)}</Alert>}
      <ReadingNote libraryId={id} estimate={estimate.data} />
      <Anchor component="button" size="sm" onClick={() => setMore(!more)} w="fit-content">
        {more ? 'Fewer options' : 'More options'}
      </Anchor>
      <Collapse expanded={more}>
        <Stack gap="xs">
          <Select
            label="Use another profile"
            placeholder="Choose a profile"
            data={[
              { value: 'none', label: "Don't re-encode video (only language changes)" },
              ...others.map((p) => ({ value: String(p.id), label: p.name })),
            ]}
            value={isPreset || choice === MIMIC ? null : choice}
            onChange={(v) => v && choose(v)}
          />
        </Stack>
      </Collapse>
      {setProfile.isError && <Alert color="red">{errorMessage(setProfile.error)}</Alert>}
      {save.isError && <Alert color="red">{errorMessage(save.error)}</Alert>}
      <NavButtons
        onBack={onBack}
        next={
          <Button
            disabled={!choice || (choice === MIMIC && !mimic.data)}
            loading={setProfile.isPending || save.isPending}
            onClick={() => {
              if (choice === 'none') {
                // No video re-encoding: no profile, so no audio step either.
                setProfile.mutate(null, { onSuccess: () => onNext() });
              } else if (choice === MIMIC) {
                saveMimic().then(
                  () => onNext(),
                  () => undefined,
                );
              } else onNext();
            }}
          >
            Next
          </Button>
        }
      />
    </Stack>
  );
}

export function AudioStep({ libraryId, onNext, onBack }: StepProps) {
  const id = libraryId ?? 0;
  const [params, setParams] = useSearchParams();
  const profiles = useProfiles();
  const save = useSaveProfile();
  const setProfile = useSetLibraryProfile(id);
  const mimicFile = params.get('mimic');
  const mimic = useMimic(params.get('choice') === MIMIC && mimicFile ? Number(mimicFile) : null);
  const base =
    params.get('choice') === MIMIC
      ? mimic.data && profiles.data && findProfile(profiles.data, mimic.data.report.settings)
      : profiles.data?.find((p) => String(p.id) === params.get('choice'));
  const keepDays = useRecycleSettings().data?.keep_days ?? 14;
  // A profile with its own audio setup (e.g. from Mimic a file) offers it first.
  const choices =
    base && hasOwnAudio(base.settings)
      ? [
          {
            key: 'profile' as const,
            title: 'As set in this profile',
            description: `${base.name}: ${describeAudio(base.settings)}.`,
          },
          ...AUDIO_CHOICES,
        ]
      : AUDIO_CHOICES;
  const audio =
    (params.get('audio') as AudioChoice | null) ??
    (base ? defaultAudioChoice(base.settings) : 'keep');
  const candidates: Record<string, ProfileSettings> = base
    ? Object.fromEntries(choices.map((c) => [c.key, withAudio(base.settings, c.key)]))
    : {};
  const estimate = useEstimate(id, candidates);
  const { ready, scale } = readiness(estimate.data);

  // A file's settings just saved as a profile: the list is still refreshing.
  const settling = params.get('choice') === MIMIC && (mimic.isLoading || profiles.isFetching);
  if (!profiles.data || (!base && settling)) return <Loader />;
  if (!base) {
    return (
      <Alert color="yellow">
        Choose a size and quality first.
        <NavButtons onBack={onBack} next={<span />} />
      </Alert>
    );
  }
  const keep = ready ? estimate.data?.results.keep : undefined;
  const extra = (key: AudioChoice): EstimateSummary | undefined => {
    const r = estimate.data?.results[key];
    return r && keep ? { ...r, saved_bytes: r.saved_bytes - keep.saved_bytes } : undefined;
  };
  const choose = (value: AudioChoice) => {
    const next = new URLSearchParams(params);
    next.set('audio', value);
    setParams(next, { replace: true });
  };
  const finish = async () => {
    const settings = withAudio(base.settings, audio);
    const existing: Profile | undefined = findProfile(profiles.data, settings);
    const profileId = existing
      ? existing.id
      : (
          await save.mutateAsync({
            name: profileName(
              base.name,
              audio,
              profiles.data.map((p) => p.name),
            ),
            settings,
          })
        ).id;
    await setProfile.mutateAsync(profileId);
    onNext();
  };
  const error = save.error ?? setProfile.error;

  return (
    <Stack>
      <Text>
        Soundtracks can take a lot of space: a film's lossless 5.1 track is often 3 to 6 GB. What
        should happen to them?
      </Text>
      <SimpleGrid cols={{ base: 1, sm: choices.length }}>
        {choices.map((c) => (
          <ChoiceCard
            key={c.key}
            selected={audio === c.key}
            title={c.title}
            description={c.description}
            onClick={() => choose(c.key)}
          >
            {c.key !== 'keep' && <Saving result={extra(c.key)} extra scale={scale} />}
          </ChoiceCard>
        ))}
      </SimpleGrid>
      <ReadingNote libraryId={id} estimate={estimate.data} />
      {withAudio(base.settings, audio).audio !== 'copy' && (
        <AudioGuide settings={withAudio(base.settings, audio)} />
      )}
      {withAudio(base.settings, audio).downmix_stereo && (
        <Alert color="orange">
          {keepDays === 0
            ? "Surround sound is gone for good: the recycle bin is off, so originals aren't kept."
            : `Surround sound is gone for good once the original leaves the recycle bin (after ${keepDays} ${keepDays === 1 ? 'day' : 'days'}).`}{' '}
          Only choose this if every screen and speaker you watch on is stereo.
        </Alert>
      )}
      {error && <Alert color="red">{errorMessage(error)}</Alert>}
      <NavButtons
        onBack={onBack}
        next={
          <Button loading={save.isPending || setProfile.isPending} onClick={() => void finish()}>
            Next
          </Button>
        }
      />
    </Stack>
  );
}
