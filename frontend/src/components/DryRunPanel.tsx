import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  List,
  Loader,
  Modal,
  Pagination,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Table,
  Text,
} from '@mantine/core';
import { IconPlayerPlay, IconWand } from '@tabler/icons-react';
import { notifications } from '@mantine/notifications';
import { Link } from 'react-router';
import { useApplyLibrary } from '../api/jobs';
import { OriginalsNote } from './KeepOriginals';
import { useTestRun } from '../api/testRun';
import { useState } from 'react';
import { errorMessage } from '../api/client';
import { type DryRunItem, type DryRunShow, useDryRun } from '../api/dryrun';
import { FLAG_LABELS } from '../api/policy';
import { formatBytes, languageName } from '../format';

function Stat({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <Card withBorder padding="sm">
      <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
        {label}
      </Text>
      <Text size="xl" fw={700}>
        {value}
      </Text>
      {hint && (
        <Text size="xs" c="dimmed">
          {hint}
        </Text>
      )}
    </Card>
  );
}

export function DryRunPanel({ libraryId }: { libraryId: number }) {
  const [started, setStarted] = useState(false);
  const [show, setShow] = useState<DryRunShow>('changes');
  const [page, setPage] = useState(1);
  const dryRun = useDryRun(libraryId, show, page, started);
  const [confirming, setConfirming] = useState(false);
  const apply = useApplyLibrary();
  const testRun = useTestRun(libraryId);

  if (!started) {
    return (
      <Card withBorder>
        <Stack align="flex-start">
          <Text size="sm">
            A dry run works out what ReelHaven would do with every file in this library, using its
            language policy. <b>Nothing is changed.</b>
          </Text>
          <Button leftSection={<IconPlayerPlay size={16} />} onClick={() => setStarted(true)}>
            Run dry run
          </Button>
        </Stack>
      </Card>
    );
  }
  if (dryRun.isPending) return <Loader />;
  if (dryRun.isError) return <Alert color="red">{errorMessage(dryRun.error)}</Alert>;
  const r = dryRun.data;
  const flagged = (r.flags.wrong_language ?? 0) + (r.flags.no_wanted_audio ?? 0);
  const approved = testRun.data?.run?.status === 'approved' && testRun.data.run.profile_is_current;
  // ADR-0020: without an approved test run only the track changes can be applied.
  const gated = r.encode > 0 && !approved;
  const total = gated ? r.remux : r.encode + r.remux;
  const applyLabel = `${gated ? 'Apply track changes to' : 'Apply to'} ${total} ${total === 1 ? 'file' : 'files'}`;

  return (
    <Stack>
      <SimpleGrid cols={{ base: 2, sm: 4 }}>
        <Stat label="Files" value={r.files} />
        <Stat
          label="Would change"
          value={r.encode + r.remux}
          hint={`${r.encode} re-encode · ${r.remux} track changes only`}
        />
        <Stat
          label="Space saved"
          value={formatBytes(r.saved_bytes)}
          hint={r.savings_unknown ? `+ ${r.savings_unknown} files with unknown savings` : undefined}
        />
        <Stat
          label="Need review"
          value={flagged + r.unreadable}
          hint="wrong language or unreadable"
        />
      </SimpleGrid>
      {gated && (
        <Alert color="blue">
          {r.encode} {r.encode === 1 ? 'file' : 'files'} would be re-encoded. Re-encoding a whole
          library needs an approved test run with the current profile first: see the Test run tab.
          Until then you can apply the track changes, and single files can be re-encoded from their
          details.
        </Alert>
      )}
      {r.waiting_for_language > 0 && (
        <Alert color="blue" title="Waiting for the language lookup">
          {r.waiting_for_language === 1 ? '1 file' : `${r.waiting_for_language} files`} won't be
          changed until{' '}
          {r.waiting_for_language === 1
            ? "its title's original language"
            : 'their original language'}{' '}
          has been looked up, so no original-language soundtrack is removed by mistake. This happens
          at the end of a scan; if Sonarr, Radarr or TMDB couldn't be reached, the next scan tries
          again.
        </Alert>
      )}
      {r.unknown_original > 0 && (
        <Alert color="yellow">
          {r.unknown_original === 1 ? '1 file has' : `${r.unknown_original} files have`} an unknown
          original language, so only your wanted languages are kept for{' '}
          {r.unknown_original === 1 ? 'it' : 'them'}. Connect Sonarr/Radarr or set languages by hand
          to improve this.
        </Alert>
      )}
      <Group justify="space-between">
        <SegmentedControl
          value={show}
          onChange={(value) => {
            setShow(value as DryRunShow);
            setPage(1);
          }}
          data={[
            { value: 'changes', label: `Changes (${r.encode + r.remux})` },
            { value: 'flagged', label: `Needs review (${flagged + r.unreadable})` },
            { value: 'all', label: `All (${r.files})` },
          ]}
        />
        <Group gap="xs">
          <Button
            variant="subtle"
            onClick={() => void dryRun.refetch()}
            loading={dryRun.isFetching}
          >
            Run again
          </Button>
          {total > 0 && (
            <Button leftSection={<IconWand size={16} />} onClick={() => setConfirming(true)}>
              {applyLabel}
            </Button>
          )}
        </Group>
      </Group>
      {r.items.length === 0 ? (
        <Text c="dimmed" size="sm">
          Nothing here.
        </Text>
      ) : (
        <Table.ScrollContainer minWidth={700}>
          <Table verticalSpacing="sm">
            <Table.Thead>
              <Table.Tr>
                <Table.Th>File</Table.Th>
                <Table.Th>Plan</Table.Th>
                <Table.Th ta="right">Saves</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {r.items.map((item) => (
                <DryRunRow key={item.file_id} item={item} />
              ))}
            </Table.Tbody>
          </Table>
        </Table.ScrollContainer>
      )}
      <Modal opened={confirming} onClose={() => setConfirming(false)} title="Apply the dry run?">
        <Stack>
          <Text size="sm">
            {gated ? (
              <>
                ReelHaven will apply the track changes to <b>{total}</b>{' '}
                {total === 1 ? 'file' : 'files'}, as listed in the dry run. The {r.encode}{' '}
                {r.encode === 1 ? 'file' : 'files'} to re-encode wait for an approved test run; they
                get their track changes when they're re-encoded.
              </>
            ) : (
              <>
                ReelHaven will process <b>{total}</b> {total === 1 ? 'file' : 'files'}: {r.encode}{' '}
                re-encoded and {r.remux} with track changes only, as listed in the dry run.
              </>
            )}
          </Text>
          <List size="sm">
            <List.Item>Each new file is checked before it replaces the original.</List.Item>
            <List.Item>
              <OriginalsNote />
            </List.Item>
            <List.Item>Files that need review are not touched.</List.Item>
          </List>
          {apply.isError && <Alert color="red">{errorMessage(apply.error)}</Alert>}
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setConfirming(false)}>
              Cancel
            </Button>
            <Button
              loading={apply.isPending}
              onClick={() =>
                apply.mutate(
                  { libraryId, expected: total, onlyTrackChanges: gated },
                  {
                    onSuccess: (result) => {
                      setConfirming(false);
                      notifications.show({
                        message: (
                          <>
                            {result.queued} {result.queued === 1 ? 'file' : 'files'} queued. Follow
                            them on the <Link to="/jobs">Jobs page</Link>.
                            {result.waiting > 0 &&
                              ` ${result.waiting} ${result.waiting === 1 ? 'waits' : 'wait'} for the language lookup; apply again after the scan.`}
                          </>
                        ),
                      });
                    },
                  },
                )
              }
            >
              {applyLabel}
            </Button>
          </Group>
        </Stack>
      </Modal>
      {r.total > 100 && (
        <Pagination total={Math.ceil(r.total / 100)} value={page} onChange={setPage} />
      )}
    </Stack>
  );
}

function DryRunRow({ item }: { item: DryRunItem }) {
  return (
    <Table.Tr>
      <Table.Td style={{ verticalAlign: 'top' }}>
        <Text size="sm" fw={500} style={{ wordBreak: 'break-word' }}>
          {item.relative_path}
        </Text>
        <Text size="xs" c="dimmed">
          Original: {item.original_language ? languageName(item.original_language) : 'unknown'}
        </Text>
      </Table.Td>
      <Table.Td style={{ verticalAlign: 'top' }}>
        <Group gap={4} mb={4}>
          {item.flags.map((flag) => (
            <Badge key={flag} size="sm" color={flag === 'dolby_vision' ? 'grape' : 'orange'}>
              {FLAG_LABELS[flag] ?? flag}
            </Badge>
          ))}
        </Group>
        {item.details.length > 0 ? (
          <List size="sm">
            {item.details.map((d) => (
              <List.Item key={d}>{d}</List.Item>
            ))}
          </List>
        ) : (
          <Text size="sm">{item.summary}</Text>
        )}
      </Table.Td>
      <Table.Td ta="right" style={{ verticalAlign: 'top', whiteSpace: 'nowrap' }}>
        <Text size="sm">
          {item.action === 'encode'
            ? item.bytes_after_estimate !== null
              ? `~${formatBytes(item.size - item.bytes_after_estimate)}`
              : '?'
            : item.action !== 'remux'
              ? '–'
              : item.removed_bytes === null
                ? '?'
                : formatBytes(item.removed_bytes)}
        </Text>
      </Table.Td>
    </Table.Tr>
  );
}
