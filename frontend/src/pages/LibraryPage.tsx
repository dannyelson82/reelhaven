import {
  Alert,
  Anchor,
  Badge,
  Button,
  Card,
  Checkbox,
  Drawer,
  Group,
  Loader,
  Pagination,
  Select,
  Progress,
  Stack,
  Table,
  Tabs,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { useDebouncedValue } from '@mantine/hooks';
import {
  IconAdjustments,
  IconAlertTriangle,
  IconLanguage,
  IconRefresh,
  IconSearch,
} from '@tabler/icons-react';
import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router';
import { errorMessage } from '../api/client';
import {
  type FileSummary,
  type ScanStatus,
  type Stream,
  useFile,
  useFiles,
  useScanStatus,
  useStartScan,
} from '../api/files';
import { useLibraries } from '../api/libraries';
import {
  SOURCE_LABELS,
  useLanguages,
  useRefreshLanguages,
  useSetTitleLanguage,
} from '../api/titles';
import { DryRunPanel } from '../components/DryRunPanel';
import { LibraryProfileSelect } from '../components/LibraryProfileSelect';
import { WatchModeSelect } from '../components/WatchModeSelect';
import { PlanView } from '../components/PlanView';
import { TestRunPanel } from '../components/TestRunPanel';
import { PolicyModal } from '../components/PolicyModal';
import { HDR_LABELS, formatBytes, formatDuration, languageName, resolutionLabel } from '../format';

const PAGE_SIZE = 50;

export function LibraryPage() {
  const libraryId = Number(useParams().id);
  const libraries = useLibraries();
  const library = libraries.data?.find((l) => l.id === libraryId);
  const [query, setQuery] = useState('');
  const [debounced] = useDebouncedValue(query, 300);
  const [problems, setProblems] = useState(false);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<number | null>(null);
  const [editingPolicy, setEditingPolicy] = useState(false);

  const scan = useScanStatus(libraryId, true);
  const scanning = scan.data?.state === 'scanning';
  const files = useFiles(libraryId, { q: debounced, problems, page, pageSize: PAGE_SIZE });
  const queryClient = useQueryClient();

  // Refresh the file list and counts when a scan finishes.
  useEffect(() => {
    if (scan.data && scan.data.state !== 'scanning') {
      void queryClient.invalidateQueries({ queryKey: ['files', libraryId] });
      void queryClient.invalidateQueries({ queryKey: ['libraries'] });
    }
  }, [scan.data?.state, scan.data, libraryId, queryClient]);

  if (libraries.isPending) return <Loader />;
  if (!library) return <Alert color="red">Library not found.</Alert>;

  return (
    <Stack>
      <Group justify="space-between" align="flex-end">
        <Stack gap={0}>
          <Anchor component={Link} to="/libraries" size="sm">
            ← Libraries
          </Anchor>
          <Title order={2}>{library.name}</Title>
          <Text size="sm" c="dimmed">
            {library.path} · {library.file_count} files
            {library.last_scan_at &&
              ` · last scanned ${new Date(library.last_scan_at).toLocaleString()}`}
          </Text>
        </Stack>
        <Group gap="xs" align="flex-start">
          <WatchModeSelect library={library} />
          <LibraryProfileSelect libraryId={libraryId} />
          <Button
            variant="default"
            leftSection={<IconAdjustments size={16} />}
            onClick={() => setEditingPolicy(true)}
          >
            Language policy
          </Button>
          <RefreshLanguagesButton libraryId={libraryId} scanning={scanning} />
          <ScanButton libraryId={libraryId} scanning={scanning} />
        </Group>
      </Group>

      {scan.data && <ScanPanel status={scan.data} />}
      {library.last_scan_error && !scanning && (
        <Alert color="red" title="The last scan failed">
          {library.last_scan_error}
        </Alert>
      )}

      <Tabs defaultValue="files" keepMounted={false}>
        <Tabs.List mb="md">
          <Tabs.Tab value="files">Files</Tabs.Tab>
          <Tabs.Tab value="dry-run">Dry run</Tabs.Tab>
          <Tabs.Tab value="test-run">Test run</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="files">
          <Stack>
            <Group>
              <TextInput
                placeholder="Search file names"
                leftSection={<IconSearch size={16} />}
                value={query}
                onChange={(e) => {
                  setQuery(e.currentTarget.value);
                  setPage(1);
                }}
                w={320}
              />
              <Checkbox
                label="Only files that couldn't be read"
                checked={problems}
                onChange={(e) => {
                  setProblems(e.currentTarget.checked);
                  setPage(1);
                }}
              />
            </Group>

            {files.isError && <Alert color="red">{errorMessage(files.error)}</Alert>}
            {files.data && files.data.total === 0 && !scanning && (
              <Card withBorder>
                <Text c="dimmed">
                  {library.file_count === 0
                    ? 'No files yet. Click "Scan library" to find the videos in this folder.'
                    : 'No files match.'}
                </Text>
              </Card>
            )}
            {files.data && files.data.total > 0 && (
              <>
                <Table.ScrollContainer minWidth={760}>
                  <Table highlightOnHover>
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>File</Table.Th>
                        <Table.Th>Original</Table.Th>
                        <Table.Th>Video</Table.Th>
                        <Table.Th>Audio</Table.Th>
                        <Table.Th>Subtitles</Table.Th>
                        <Table.Th ta="right">Size</Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {files.data.items.map((file) => (
                        <FileRow key={file.id} file={file} onOpen={() => setSelected(file.id)} />
                      ))}
                    </Table.Tbody>
                  </Table>
                </Table.ScrollContainer>
                {files.data.total > PAGE_SIZE && (
                  <Pagination
                    total={Math.ceil(files.data.total / PAGE_SIZE)}
                    value={page}
                    onChange={setPage}
                  />
                )}
              </>
            )}
          </Stack>
        </Tabs.Panel>
        <Tabs.Panel value="dry-run">
          <DryRunPanel libraryId={libraryId} />
        </Tabs.Panel>
        <Tabs.Panel value="test-run">
          <TestRunPanel libraryId={libraryId} />
        </Tabs.Panel>
      </Tabs>
      <FileDrawer libraryId={libraryId} fileId={selected} onClose={() => setSelected(null)} />
      {editingPolicy && (
        <PolicyModal libraryId={libraryId} onClose={() => setEditingPolicy(false)} />
      )}
    </Stack>
  );
}

function ScanButton({ libraryId, scanning }: { libraryId: number; scanning: boolean }) {
  const start = useStartScan(libraryId);
  return (
    <Stack gap={4} align="flex-end">
      <Button
        leftSection={<IconRefresh size={16} />}
        loading={start.isPending || scanning}
        onClick={() => start.mutate()}
      >
        Scan library
      </Button>
      {start.isError && (
        <Text size="xs" c="red">
          {errorMessage(start.error)}
        </Text>
      )}
    </Stack>
  );
}

function RefreshLanguagesButton({ libraryId, scanning }: { libraryId: number; scanning: boolean }) {
  const refresh = useRefreshLanguages(libraryId);
  return (
    <Button
      variant="default"
      leftSection={<IconLanguage size={16} />}
      loading={refresh.isPending}
      disabled={scanning}
      onClick={() => refresh.mutate()}
    >
      Refresh languages
    </Button>
  );
}

function ScanPanel({ status }: { status: ScanStatus }) {
  if (status.state === 'scanning') {
    const pct = status.to_probe ? (100 * status.probed) / status.to_probe : 0;
    const label =
      status.phase === 'listing'
        ? 'Looking for video files…'
        : status.phase === 'languages'
          ? 'Looking up original languages…'
          : `Reading files: ${status.probed} of ${status.to_probe}`;
    return (
      <Card withBorder>
        <Stack gap="xs">
          <Text size="sm">{label}</Text>
          <Progress value={pct} animated={status.phase === 'listing'} />
        </Stack>
      </Card>
    );
  }
  if (status.state === 'error') {
    return (
      <Alert color="red" title="Scan failed">
        {status.error}
      </Alert>
    );
  }
  const parts = [
    status.found > 0 && `${status.found} video files`,
    status.to_probe && `${status.to_probe} read`,
    status.moved && `${status.moved} moved`,
    status.removed && `${status.removed} gone`,
    status.failed && `${status.failed} couldn't be read`,
    status.languages_resolved && `${status.languages_resolved} original languages found`,
    status.languages_unknown && `${status.languages_unknown} titles with unknown language`,
  ].filter(Boolean);
  return (
    <Alert
      color={status.failed || status.language_errors.length ? 'yellow' : 'teal'}
      title="Finished"
    >
      {parts.join(' · ')}
      {status.unstable > 0 &&
        ` · ${status.unstable} still being copied (they'll be picked up by the next scan)`}
      {status.language_errors.length > 0 && (
        <Text size="sm" c="red" mt={4}>
          Language lookup problems: {status.language_errors.join('; ')}
        </Text>
      )}
    </Alert>
  );
}

function LanguageBadges({ codes }: { codes: (string | null)[] }) {
  if (codes.length === 0)
    return (
      <Text size="sm" c="dimmed">
        none
      </Text>
    );
  return (
    <Group gap={4}>
      {codes.map((code, i) => (
        <Badge key={i} variant="light" color={code ? 'gray' : 'yellow'} tt="none">
          {languageName(code)}
        </Badge>
      ))}
    </Group>
  );
}

function FileRow({ file, onOpen }: { file: FileSummary; onOpen: () => void }) {
  const name = file.relative_path.split('/').pop();
  const folder = file.relative_path.slice(0, -(name?.length ?? 0));
  return (
    <Table.Tr style={{ cursor: 'pointer' }} onClick={onOpen}>
      <Table.Td>
        <Text size="sm" fw={500}>
          {name}
        </Text>
        <Text size="xs" c="dimmed">
          {folder}
        </Text>
      </Table.Td>
      <Table.Td>
        <OriginalBadge language={file.original_language} source={file.language_source} />
      </Table.Td>
      <Table.Td>
        {file.status === 'probe_failed' ? (
          <Badge color="red" leftSection={<IconAlertTriangle size={12} />}>
            Can't read
          </Badge>
        ) : (
          <Group gap={4}>
            <Badge variant="outline" tt="uppercase">
              {file.video_codec ?? '?'}
            </Badge>
            {resolutionLabel(file.width, file.height) && (
              <Badge variant="outline">{resolutionLabel(file.width, file.height)}</Badge>
            )}
            {file.hdr && HDR_LABELS[file.hdr] && (
              <Badge color="grape">{HDR_LABELS[file.hdr]}</Badge>
            )}
          </Group>
        )}
      </Table.Td>
      <Table.Td>
        <LanguageBadges codes={file.audio_languages} />
      </Table.Td>
      <Table.Td>
        <LanguageBadges codes={file.subtitle_languages} />
      </Table.Td>
      <Table.Td ta="right">
        <Text size="sm" style={{ whiteSpace: 'nowrap' }}>
          {formatBytes(file.size)}
        </Text>
      </Table.Td>
    </Table.Tr>
  );
}

function OriginalBadge({ language, source }: { language: string | null; source: string | null }) {
  if (!language) {
    return (
      <Badge variant="light" color="gray" tt="none">
        unknown
      </Badge>
    );
  }
  return (
    <Badge
      variant="light"
      color="teal"
      tt="none"
      title={`From ${SOURCE_LABELS[source ?? ''] ?? source}`}
    >
      {languageName(language)}
    </Badge>
  );
}

function OriginalLanguageEditor({
  libraryId,
  titleId,
  language,
  source,
}: {
  libraryId: number;
  titleId: number;
  language: string | null;
  source: string | null;
}) {
  const languages = useLanguages();
  const setLanguage = useSetTitleLanguage(libraryId);
  return (
    <Card withBorder>
      <Stack gap="xs">
        <Text size="sm" fw={500}>
          Original language: {language ? languageName(language) : 'unknown'}
          <Text span size="sm" c="dimmed">
            {' '}
            ({SOURCE_LABELS[source ?? 'unknown'] ?? source})
          </Text>
        </Text>
        <Group gap="xs" align="flex-end">
          <Select
            label="Change for every file of this title"
            placeholder="Choose a language"
            searchable
            data={(languages.data ?? []).map((l) => ({ value: l.code, label: l.name }))}
            value={source === 'manual' ? language : null}
            onChange={(value) => value && setLanguage.mutate({ titleId, language: value })}
            w={280}
          />
          {source === 'manual' && (
            <Button
              variant="subtle"
              onClick={() => setLanguage.mutate({ titleId, language: null })}
              loading={setLanguage.isPending}
            >
              Go back to automatic
            </Button>
          )}
        </Group>
        {setLanguage.isError && (
          <Text size="sm" c="red">
            {errorMessage(setLanguage.error)}
          </Text>
        )}
      </Stack>
    </Card>
  );
}

function streamFlags(stream: Stream): string[] {
  return [
    stream.default && 'default',
    stream.forced && 'forced',
    stream.hearing_impaired && 'SDH',
    stream.commentary && 'commentary',
    stream.image_based && 'image-based',
  ].filter((x): x is string => Boolean(x));
}

function streamDetails(stream: Stream): string {
  if (stream.kind === 'video') {
    return [
      stream.width && `${stream.width}×${stream.height}`,
      stream.bit_depth && `${stream.bit_depth}-bit`,
      stream.frame_rate && `${stream.frame_rate} fps`,
      stream.hdr && HDR_LABELS[stream.hdr],
    ]
      .filter(Boolean)
      .join(' · ');
  }
  if (stream.kind === 'audio') {
    return [
      stream.channel_layout ?? (stream.channels && `${stream.channels} ch`),
      stream.bit_rate && `${Math.round(stream.bit_rate / 1000)} kb/s`,
    ]
      .filter(Boolean)
      .join(' · ');
  }
  return '';
}

function FileDrawer({
  libraryId,
  fileId,
  onClose,
}: {
  libraryId: number;
  fileId: number | null;
  onClose: () => void;
}) {
  const file = useFile(fileId);
  return (
    <Drawer
      opened={fileId !== null}
      onClose={onClose}
      position="right"
      size="xl"
      title="File details"
    >
      {file.isPending && fileId !== null && <Loader />}
      {file.isError && <Alert color="red">{errorMessage(file.error)}</Alert>}
      {file.data && (
        <Stack>
          <Text fw={600} style={{ wordBreak: 'break-all' }}>
            {file.data.relative_path}
          </Text>
          <Text size="sm" c="dimmed">
            {formatBytes(file.data.size)} · {formatDuration(file.data.duration_s)}
            {file.data.container && ` · ${file.data.container.split(',')[0]}`}
          </Text>
          {file.data.title_id !== null && (
            <OriginalLanguageEditor
              libraryId={libraryId}
              titleId={file.data.title_id}
              language={file.data.original_language}
              source={file.data.language_source}
            />
          )}
          {file.data.status === 'ok' && <PlanView fileId={file.data.id} />}
          {file.data.probe_error && (
            <Alert color="red" title="ffprobe couldn't read this file">
              <Text size="sm" style={{ whiteSpace: 'pre-wrap' }}>
                {file.data.probe_error}
              </Text>
            </Alert>
          )}
          {file.data.streams.length > 0 && (
            <Table>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>#</Table.Th>
                  <Table.Th>Type</Table.Th>
                  <Table.Th>Codec</Table.Th>
                  <Table.Th>Language</Table.Th>
                  <Table.Th>Title</Table.Th>
                  <Table.Th>Details</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {file.data.streams.map((stream) => (
                  <Table.Tr key={stream.index}>
                    <Table.Td>{stream.index}</Table.Td>
                    <Table.Td>{stream.kind}</Table.Td>
                    <Table.Td>{stream.codec}</Table.Td>
                    <Table.Td>
                      {stream.kind === 'audio' || stream.kind === 'subtitle'
                        ? languageName(stream.language)
                        : ''}
                    </Table.Td>
                    <Table.Td>{stream.title}</Table.Td>
                    <Table.Td>
                      <Group gap={4}>
                        <Text size="xs">{streamDetails(stream)}</Text>
                        {streamFlags(stream).map((flag) => (
                          <Badge key={flag} size="xs" variant="light">
                            {flag}
                          </Badge>
                        ))}
                      </Group>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
        </Stack>
      )}
    </Drawer>
  );
}
