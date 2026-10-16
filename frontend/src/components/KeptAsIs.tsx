import {
  Alert,
  Card,
  Loader,
  Pagination,
  SegmentedControl,
  Stack,
  Text,
  Title,
} from '@mantine/core';
import { useState } from 'react';
import { errorMessage } from '../api/client';
import { REVIEW_KINDS, type ReviewKind, useReview } from '../api/review';
import { formatBytes } from '../format';

const PAGE_SIZE = 50;

/** Files ReelHaven left as they were on purpose (ADR-0035): results, not decisions. */
export function KeptAsIs() {
  const [kind, setKind] = useState<ReviewKind>('no_gain');
  const [page, setPage] = useState(1);
  const review = useReview({ kind, page }, PAGE_SIZE);
  const counts = review.data?.counts;
  const label = (k: ReviewKind) => {
    const name = REVIEW_KINDS.find((r) => r.kind === k)?.label ?? k;
    return counts ? `${name} (${counts[k]})` : name;
  };
  return (
    <Stack>
      <Title order={4}>Kept as is</Title>
      <Text size="sm" c="dimmed" maw={720}>
        Files ReelHaven left unchanged on purpose. Nothing to decide here; they're listed so you can
        see what was kept and why.
      </Text>
      <SegmentedControl
        w="fit-content"
        value={kind}
        onChange={(value) => {
          setKind(value as ReviewKind);
          setPage(1);
        }}
        data={[
          { value: 'no_gain', label: label('no_gain') },
          { value: 'skipped', label: label('skipped') },
        ]}
      />
      <Text size="sm" c="dimmed">
        {REVIEW_KINDS.find((r) => r.kind === kind)?.about}
      </Text>
      {review.isPending && <Loader />}
      {review.isError && <Alert color="red">{errorMessage(review.error)}</Alert>}
      {review.data && review.data.items.length === 0 && <Text c="dimmed">Nothing here.</Text>}
      {review.data?.items.map((item) => (
        <Card key={`${item.kind}-${item.file_id}`} withBorder padding="sm">
          <Text fw={500} style={{ wordBreak: 'break-word' }}>
            {item.relative_path}
          </Text>
          <Text size="xs" c="dimmed">
            {item.library_name} · {formatBytes(item.size)}
          </Text>
          <Text size="sm">{item.detail}</Text>
        </Card>
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
