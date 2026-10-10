// The review page (ADR-0032): every file that needs a decision, in one place.
import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Loader,
  Modal,
  Pagination,
  Stack,
  Switch,
  Tabs,
  Text,
  Title,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useState } from 'react';
import { Link, useSearchParams } from 'react-router';
import { errorMessage } from '../api/client';
import { useRetryJob } from '../api/jobs';
import {
  REVIEW_KINDS,
  type ReviewItem,
  type ReviewKind,
  useIgnore,
  useReview,
  useWrongLanguageAction,
} from '../api/review';
import { formatBytes, languageName } from '../format';

const PAGE_SIZE = 100;

export function ReviewPage() {
  const [params, setParams] = useSearchParams();
  const kind = (params.get('kind') as ReviewKind | null) ?? 'wrong_language';
  const [showIgnored, setShowIgnored] = useState(false);
  const [page, setPage] = useState(1);
  const review = useReview({ kind, showIgnored, page }, PAGE_SIZE);
  const about = REVIEW_KINDS.find((k) => k.kind === kind)?.about;

  return (
    <Stack>
      <Title order={2}>Review</Title>
      <Text c="dimmed" maw={720}>
        Files that need a decision. Nothing here changes on its own; <b>Ignore</b> hides a file
        until it changes.
      </Text>
      <Tabs
        value={kind}
        onChange={(value) => {
          if (!value) return;
          setPage(1);
          setParams({ kind: value });
        }}
      >
        <Tabs.List>
          {REVIEW_KINDS.map((k) => (
            <Tabs.Tab
              key={k.kind}
              value={k.kind}
              rightSection={
                review.data && review.data.counts[k.kind] > 0 ? (
                  <Badge size="sm" variant="light" color={k.kind === 'waiting' ? 'gray' : 'orange'}>
                    {review.data.counts[k.kind]}
                  </Badge>
                ) : undefined
              }
            >
              {k.label}
            </Tabs.Tab>
          ))}
        </Tabs.List>
      </Tabs>
      <Group justify="space-between">
        <Text size="sm" c="dimmed">
          {about}
        </Text>
        <Switch
          label={`Show ignored${review.data && review.data.ignored > 0 ? ` (${review.data.ignored})` : ''}`}
          checked={showIgnored}
          onChange={(e) => {
            setPage(1);
            setShowIgnored(e.currentTarget.checked);
          }}
        />
      </Group>
      {review.isPending && <Loader />}
      {review.isError && <Alert color="red">{errorMessage(review.error)}</Alert>}
      {review.data && review.data.items.length === 0 && <Text c="dimmed">Nothing here.</Text>}
      {review.data?.items.map((item) => (
        <ReviewCard key={`${item.kind}-${item.file_id}`} item={item} />
      ))}
      {review.data && review.data.total > PAGE_SIZE && (
        <Pagination
          total={Math.ceil(review.data.total / PAGE_SIZE)}
          value={page}
          onChange={setPage}
        />
      )}
    </Stack>
  );
}

function ReviewCard({ item }: { item: ReviewItem }) {
  const ignore = useIgnore();
  const retry = useRetryJob();
  const act = useWrongLanguageAction();
  const [confirm, setConfirm] = useState<'quarantine' | 'delete' | null>(null);
  return (
    <Card withBorder padding="sm" opacity={item.ignored ? 0.6 : 1}>
      <Group justify="space-between" align="flex-start" wrap="nowrap">
        <Stack gap={2} style={{ minWidth: 0 }}>
          <Text fw={500} style={{ wordBreak: 'break-word' }}>
            {item.relative_path}
          </Text>
          <Text size="xs" c="dimmed">
            {item.library_name} · {formatBytes(item.size)}
            {item.ignored && ' · ignored'}
          </Text>
          <Text size="sm">
            {item.kind === 'wrong_language'
              ? `Audio: ${item.audio_languages.length > 0 ? item.audio_languages.map(languageName).join(', ') : 'no tagged language'}${item.original_language ? ` · original language: ${languageName(item.original_language)}` : ''}`
              : item.detail}
          </Text>
          {(ignore.isError || retry.isError || act.isError) && (
            <Text size="xs" c="red">
              {errorMessage(ignore.error ?? retry.error ?? act.error)}
            </Text>
          )}
        </Stack>
        <Group gap="xs" wrap="nowrap">
          {item.kind === 'wrong_language' && !item.ignored && (
            <>
              <Button size="xs" variant="light" onClick={() => setConfirm('quarantine')}>
                Quarantine
              </Button>
              <Button size="xs" variant="light" color="red" onClick={() => setConfirm('delete')}>
                Delete
              </Button>
            </>
          )}
          {item.kind === 'failed' && item.job_id !== null && (
            <Button
              size="xs"
              variant="light"
              loading={retry.isPending}
              onClick={() => retry.mutate(item.job_id as number)}
            >
              Try again
            </Button>
          )}
          <Button size="xs" variant="default" component={Link} to={`/libraries/${item.library_id}`}>
            Open library
          </Button>
          {item.kind !== 'waiting' && (
            <Button
              size="xs"
              variant="subtle"
              loading={ignore.isPending}
              onClick={() =>
                ignore.mutate({ file_id: item.file_id, kind: item.kind, ignored: !item.ignored })
              }
            >
              {item.ignored ? 'Show again' : 'Ignore'}
            </Button>
          )}
        </Group>
      </Group>
      <Modal
        opened={confirm !== null}
        onClose={() => setConfirm(null)}
        title={confirm === 'delete' ? 'Delete this file?' : 'Quarantine this file?'}
      >
        <Stack>
          <Text size="sm">
            <b>{item.relative_path}</b> leaves the library
            {confirm === 'delete'
              ? ' for the recycle bin'
              : ' for the quarantine (Recycle bin page, Quarantine tab)'}
            , kept for the recycle bin&apos;s days to keep. Sonarr or Radarr is then asked to
            blocklist this release and search for another.
          </Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setConfirm(null)}>
              Cancel
            </Button>
            <Button
              color={confirm === 'delete' ? 'red' : undefined}
              loading={act.isPending}
              onClick={() =>
                confirm &&
                act.mutate(
                  { file_id: item.file_id, action: confirm },
                  {
                    onSuccess: () => {
                      notifications.show({
                        message:
                          confirm === 'delete'
                            ? 'Deleting; another release is being searched for.'
                            : 'Quarantining; another release is being searched for.',
                      });
                      setConfirm(null);
                    },
                  },
                )
              }
            >
              {confirm === 'delete' ? 'Delete' : 'Quarantine'}
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Card>
  );
}
