import { Alert, Badge, Card, Group, List, Loader, Stack, Text } from '@mantine/core';
import { FLAG_LABELS, usePlan } from '../api/policy';
import { formatBytes } from '../format';

/** What ReelHaven would do with one file. */
export function PlanView({ fileId }: { fileId: number }) {
  const plan = usePlan(fileId);
  if (plan.isPending) return <Loader size="sm" />;
  if (plan.isError || !plan.data) return null;
  const p = plan.data;
  return (
    <Card withBorder>
      <Stack gap="xs">
        <Group gap="xs">
          <Text size="sm" fw={500}>
            What ReelHaven would do
          </Text>
          <Badge color={p.action === 'remux' ? 'blue' : 'gray'}>
            {p.action === 'remux' ? 'Remux' : 'Nothing'}
          </Badge>
          {p.flags.map((flag) => (
            <Badge key={flag} color={flag === 'dolby_vision' ? 'grape' : 'orange'}>
              {FLAG_LABELS[flag] ?? flag}
            </Badge>
          ))}
        </Group>
        <Text size="sm">{p.summary}</Text>
        {p.details.length > 0 && (
          <List size="sm">
            {p.details.map((d) => (
              <List.Item key={d}>{d}</List.Item>
            ))}
          </List>
        )}
        {p.action === 'remux' && p.removed_bytes !== null && p.removed_bytes > 0 && (
          <Text size="xs" c="dimmed">
            Saves about {formatBytes(p.removed_bytes)}.
          </Text>
        )}
        {p.flags.includes('wrong_language') && (
          <Alert color="orange">
            This file doesn't have audio in a language you want. It's left untouched for you to
            review.
          </Alert>
        )}
      </Stack>
    </Card>
  );
}
