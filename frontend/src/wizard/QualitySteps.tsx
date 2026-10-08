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
import { Link, useSearchParams } from 'react-router';
import { errorMessage } from '../api/client';
import {
  type Profile,
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
  type AudioChoice,
  PRESETS,
  findProfile,
  profileName,
  withAudio,
} from './choices';
import type { StepProps } from './LibrarySteps';

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
  const [more, setMore] = useState(false);
  const builtins = Object.fromEntries(
    (profiles.data ?? []).filter((p) => p.builtin).map((p) => [p.name, p]),
  );
  const presets = PRESETS.map((preset) => ({ ...preset, profile: builtins[preset.builtin] }));
  const candidates = Object.fromEntries(
    presets.filter((p) => p.profile).map((p) => [String(p.profile.id), p.profile.settings]),
  );
  const estimate = useEstimate(id, candidates);
  const { ready, scale } = readiness(estimate.data);
  const balancedId = builtins.Balanced ? String(builtins.Balanced.id) : null;
  const choice = params.get('choice') ?? balancedId;
  const others = (profiles.data ?? []).filter((p) => !presets.some((x) => x.profile?.id === p.id));

  if (!profiles.data) return <Loader />;
  const choose = (value: string) => {
    const next = new URLSearchParams(params);
    next.set('choice', value);
    setParams(next, { replace: true });
  };

  return (
    <Stack>
      <Text>
        How small should your files get? Each choice shows what it would save on this library; the
        test run in a moment shows the real result.
      </Text>
      <SimpleGrid cols={{ base: 1, sm: 3 }}>
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
      </SimpleGrid>
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
            value={presets.some((p) => String(p.profile?.id) === choice) ? null : choice}
            onChange={(v) => v && choose(v)}
          />
          <Text size="xs" c="dimmed">
            To copy the size and quality of a file you like, use{' '}
            <Anchor component={Link} to="/profiles" size="xs">
              Mimic a file
            </Anchor>{' '}
            on the Profiles page, then come back here.
          </Text>
        </Stack>
      </Collapse>
      {setProfile.isError && <Alert color="red">{errorMessage(setProfile.error)}</Alert>}
      <NavButtons
        onBack={onBack}
        next={
          <Button
            disabled={!choice}
            loading={setProfile.isPending}
            onClick={() => {
              if (choice === 'none') {
                // No video re-encoding: no profile, so no audio step either.
                setProfile.mutate(null, { onSuccess: () => onNext() });
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
  const base = profiles.data?.find((p) => String(p.id) === params.get('choice'));
  const keepDays = useRecycleSettings().data?.keep_days ?? 14;
  const audio = (params.get('audio') as AudioChoice | null) ?? 'keep';
  const candidates: Record<string, ProfileSettings> = base
    ? Object.fromEntries(AUDIO_CHOICES.map((c) => [c.key, withAudio(base.settings, c.key)]))
    : {};
  const estimate = useEstimate(id, candidates);
  const { ready, scale } = readiness(estimate.data);

  if (!profiles.data) return <Loader />;
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
      <SimpleGrid cols={{ base: 1, sm: 3 }}>
        {AUDIO_CHOICES.map((c) => (
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
      {audio === 'stereo' && (
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
