import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  List,
  Loader,
  Modal,
  Select,
  Stack,
  Text,
  TextInput,
  UnstyledButton,
} from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import { IconSearch } from '@tabler/icons-react';
import { useState } from 'react';
import { errorMessage } from '../api/client';
import { useFiles } from '../api/files';
import { useLibraries } from '../api/libraries';
import { type MimicReport, describe, useMimic } from '../api/profiles';
import { HDR_LABELS, formatBytes, resolutionLabel } from '../format';

/** Pick a library file and read how it was made (ARCHITECTURE.md §7.2, ADR-0022). */
export function MimicModal({
  onClose,
  onUse,
}: {
  onClose: () => void;
  onUse: (file: string, report: MimicReport) => void;
}) {
  const libraries = useLibraries();
  const [libraryId, setLibraryId] = useState<number | null>(null);
  const [query, setQuery] = useState('');
  const [debounced] = useDebouncedValue(query, 300);
  const [fileId, setFileId] = useState<number | null>(null);
  const library = libraryId ?? libraries.data?.[0]?.id ?? null;

  return (
    <Modal opened onClose={onClose} title="Mimic a file" size="lg">
      {fileId === null ? (
        <Stack>
          <Text size="sm" c="dimmed">
            Pick a file whose size and quality you like. ReelHaven reads how it was made and builds
            a profile that reproduces it across a library. The resolution is never changed, and the
            file itself isn&apos;t touched.
          </Text>
          {libraries.data?.length === 0 && (
            <Alert color="yellow">Add a library first: the sample must be in one.</Alert>
          )}
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
          {library !== null && (
            <FileChoices libraryId={library} query={debounced} onPick={setFileId} />
          )}
        </Stack>
      ) : (
        <MimicResult
          fileId={fileId}
          onBack={() => setFileId(null)}
          onUse={(file, report) => onUse(file, report)}
        />
      )}
    </Modal>
  );
}

function FileChoices({
  libraryId,
  query,
  onPick,
}: {
  libraryId: number;
  query: string;
  onPick: (fileId: number) => void;
}) {
  const files = useFiles(libraryId, { q: query, problems: false, page: 1, pageSize: 15 });
  if (files.isPending) return <Loader size="sm" />;
  if (files.isError) return <Alert color="red">{errorMessage(files.error)}</Alert>;
  const readable = files.data.items.filter((f) => f.status === 'ok' && f.video_codec);
  if (readable.length === 0) {
    return (
      <Text size="sm" c="dimmed">
        No video files match.
      </Text>
    );
  }
  return (
    <Stack gap={4}>
      {readable.map((file) => {
        const name = file.relative_path.split('/').pop();
        return (
          <UnstyledButton key={file.id} onClick={() => onPick(file.id)}>
            <Card withBorder padding="xs">
              <Group justify="space-between" wrap="nowrap">
                <Stack gap={0} style={{ minWidth: 0 }}>
                  <Text size="sm" fw={500} truncate>
                    {name}
                  </Text>
                  <Text size="xs" c="dimmed" truncate>
                    {file.relative_path}
                  </Text>
                </Stack>
                <Group gap={4} wrap="nowrap">
                  <Badge variant="outline" tt="uppercase">
                    {file.video_codec}
                  </Badge>
                  {resolutionLabel(file.width, file.height) && (
                    <Badge variant="outline">{resolutionLabel(file.width, file.height)}</Badge>
                  )}
                  {file.hdr && HDR_LABELS[file.hdr] && (
                    <Badge color="grape">{HDR_LABELS[file.hdr]}</Badge>
                  )}
                  <Text size="xs" style={{ whiteSpace: 'nowrap' }}>
                    {formatBytes(file.size)}
                  </Text>
                </Group>
              </Group>
            </Card>
          </UnstyledButton>
        );
      })}
    </Stack>
  );
}

function MimicResult({
  fileId,
  onBack,
  onUse,
}: {
  fileId: number;
  onBack: () => void;
  onUse: (file: string, report: MimicReport) => void;
}) {
  const mimic = useMimic(fileId);
  if (mimic.isPending) {
    return (
      <Group>
        <Loader size="sm" />
        <Text size="sm">Reading the file…</Text>
      </Group>
    );
  }
  if (mimic.isError) {
    return (
      <Stack>
        <Alert color="red">{errorMessage(mimic.error)}</Alert>
        <Group>
          <Button variant="default" onClick={onBack}>
            Back
          </Button>
        </Group>
      </Stack>
    );
  }
  const { file, report } = mimic.data;
  const s = report.sample;
  const facts = [
    String(s.codec ?? '?').toUpperCase(),
    s.bit_depth && `${s.bit_depth}-bit`,
    s.width && `${s.width}×${s.height}`,
    s.video_kbps && `video ${(Number(s.video_kbps) / 1000).toFixed(1)} Mbit/s`,
    s.encoder && `made with ${s.encoder}`,
  ].filter(Boolean);
  return (
    <Stack>
      <Stack gap={2}>
        <Text fw={600} style={{ wordBreak: 'break-word' }}>
          {file}
        </Text>
        <Text size="sm" c="dimmed">
          {facts.join(' · ')}
        </Text>
      </Stack>
      <List size="sm">
        {report.notes.map((note) => (
          <List.Item key={note}>{note}</List.Item>
        ))}
      </List>
      <Card withBorder>
        <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
          Suggested profile
        </Text>
        <Text size="sm" fw={500}>
          {describe(report.settings)}
        </Text>
      </Card>
      <Group justify="space-between">
        <Button variant="default" onClick={onBack}>
          Pick another file
        </Button>
        <Button onClick={() => onUse(file, report)}>Use these settings</Button>
      </Group>
    </Stack>
  );
}
