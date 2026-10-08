// The first library steps of the setup wizard (ADR-0026): folder, scan, languages.
import {
  Alert,
  Button,
  Code,
  Group,
  Loader,
  SegmentedControl,
  Select,
  Stack,
  Switch,
  Text,
  TextInput,
} from '@mantine/core';
import { useEffect, useRef, useState } from 'react';
import { errorMessage } from '../api/client';
import { useScanStatus, useStartScan } from '../api/files';
import { LIBRARY_TYPES, type LibraryType, useCreateLibrary, useLibraries } from '../api/libraries';
import { type LanguagePolicy, usePolicy, useSavePolicy } from '../api/policy';
import { type LanguageOption, useLanguages } from '../api/titles';
import { FolderPicker } from '../components/FolderPicker';
import { ScanProgress } from '../components/ScanProgress';
import { browserLanguage, guessLibrary } from './guess';

export interface StepProps {
  libraryId: number | null;
  onNext: (libraryId?: number) => void;
  onBack?: () => void;
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

export function FolderStep({ onNext, onBack }: StepProps) {
  const create = useCreateLibrary();
  const [path, setPath] = useState('');
  const [name, setName] = useState('');
  const [type, setType] = useState<LibraryType>('movies');
  const [touched, setTouched] = useState(false);

  const pick = (picked: string) => {
    setPath(picked);
    if (!touched) {
      const guess = guessLibrary(picked);
      setName(guess.name);
      setType(guess.type);
    }
  };

  return (
    <Stack>
      <Text>
        Which folder holds the videos? Pick one library at a time, for example your Movies folder,
        then your TV folder.
      </Text>
      <FolderPicker value={path} onChange={pick} />
      <Text size="sm">
        Selected: <Code>/media/{path}</Code>
      </Text>
      <Group grow align="flex-start">
        <TextInput
          label="Name"
          value={name}
          onChange={(e) => {
            setName(e.currentTarget.value);
            setTouched(true);
          }}
        />
        <div>
          <Text size="sm" fw={500} mb={4}>
            What's in it
          </Text>
          <SegmentedControl
            data={LIBRARY_TYPES}
            value={type}
            onChange={(v) => {
              setType(v as LibraryType);
              setTouched(true);
            }}
          />
        </div>
      </Group>
      <Text size="sm" c="dimmed">
        Nothing in the folder is changed yet.
      </Text>
      {create.isError && <Alert color="red">{errorMessage(create.error)}</Alert>}
      <NavButtons
        onBack={onBack}
        next={
          <Button
            disabled={!path || !name.trim()}
            loading={create.isPending}
            onClick={() =>
              create.mutate(
                { name: name.trim(), type, path },
                { onSuccess: (library) => onNext(library.id) },
              )
            }
          >
            Next
          </Button>
        }
      />
    </Stack>
  );
}

export function ScanStep({ libraryId, onNext, onBack }: StepProps) {
  const id = libraryId ?? 0;
  const start = useStartScan(id);
  const libraries = useLibraries();
  const library = libraries.data?.find((l) => l.id === id);
  const status = useScanStatus(id, true);
  const started = useRef(false);

  useEffect(() => {
    // Read the folder once when the step opens (unless it was scanned already).
    if (!started.current && library && !library.last_scan_at && !library.scanning) {
      started.current = true;
      start.mutate();
    }
  }, [library, start]);

  const scan = status.data;
  const scanning = scan?.state === 'scanning' || start.isPending;
  const files = library?.file_count ?? 0;
  return (
    <Stack>
      <Text>ReelHaven reads every video file to see its picture, sound and subtitles.</Text>
      {scanning && scan && (
        <Stack gap="xs">
          <ScanProgress status={scan} />
          <Text size="xs" c="dimmed">
            Large libraries take a few minutes. You can leave this page; it carries on.
          </Text>
        </Stack>
      )}
      {scanning && !scan && <Loader size="sm" />}
      {scan?.state === 'error' && <Alert color="red">{scan.error}</Alert>}
      {!scanning && library?.last_scan_at && files > 0 && (
        <Alert color="teal">
          Found {files} video {files === 1 ? 'file' : 'files'} in {library.name}.
        </Alert>
      )}
      {!scanning && library?.last_scan_at && files === 0 && (
        <Alert color="yellow" title="No videos found">
          This folder doesn't contain video files ReelHaven can read. Check that it's the right
          folder, then scan again.
          <Group mt="xs">
            <Button size="xs" variant="light" onClick={() => start.mutate()}>
              Scan again
            </Button>
          </Group>
        </Alert>
      )}
      <NavButtons
        onBack={onBack}
        next={
          <Button disabled={scanning || files === 0} onClick={() => onNext()}>
            Next
          </Button>
        }
      />
    </Stack>
  );
}

export function LanguagesStep({ libraryId, onNext, onBack }: StepProps) {
  const id = libraryId ?? 0;
  const languages = useLanguages();
  const policy = usePolicy(id);
  if (!languages.data || !policy.data) return <Loader />;
  const current = policy.data.keep_languages[0];
  // A fresh library has the default (English): suggest the browser's language instead.
  const suggested =
    current && current !== 'eng'
      ? current
      : browserLanguage(languages.data, navigator.languages ?? []);
  return (
    <LanguagesForm
      libraryId={id}
      languages={languages.data}
      policy={policy.data}
      suggested={suggested}
      onNext={onNext}
      onBack={onBack}
    />
  );
}

function LanguagesForm({
  libraryId,
  languages,
  policy,
  suggested,
  onNext,
  onBack,
}: {
  libraryId: number;
  languages: LanguageOption[];
  policy: LanguagePolicy;
  suggested: string;
  onNext: () => void;
  onBack?: () => void;
}) {
  const save = useSavePolicy(libraryId);
  const [language, setLanguage] = useState(suggested);
  const [keepOriginal, setKeepOriginal] = useState(policy.keep_original);
  return (
    <Stack>
      <Text>
        Many files carry soundtracks and subtitles in languages nobody in your home watches.
        ReelHaven keeps the ones you want and removes the rest.
      </Text>
      <Select
        label="Which language do you speak?"
        description="Audio and subtitles in this language are always kept."
        searchable
        allowDeselect={false}
        data={languages.map((l) => ({ value: l.code, label: l.name }))}
        value={language}
        onChange={(v) => v && setLanguage(v)}
      />
      <Switch
        label="Also keep each title's original language"
        description="For example the Japanese soundtrack of a Japanese film. Recommended."
        checked={keepOriginal}
        onChange={(e) => setKeepOriginal(e.currentTarget.checked)}
      />
      <Text size="sm" c="dimmed">
        Files with no soundtrack in these languages are never changed; they're listed for you to
        review instead.
      </Text>
      {save.isError && <Alert color="red">{errorMessage(save.error)}</Alert>}
      <NavButtons
        onBack={onBack}
        next={
          <Button
            loading={save.isPending}
            onClick={() =>
              save.mutate(
                {
                  ...policy,
                  keep_languages: [
                    language,
                    // Replace the untouched default (English); keep languages added on purpose.
                    ...(isDefault(policy.keep_languages) ? [] : policy.keep_languages).filter(
                      (l) => l !== language,
                    ),
                  ],
                  keep_original: keepOriginal,
                },
                { onSuccess: () => onNext() },
              )
            }
          >
            Next
          </Button>
        }
      />
    </Stack>
  );
}

const isDefault = (languages: string[]) => languages.length === 1 && languages[0] === 'eng';
