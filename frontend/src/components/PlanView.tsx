import { Alert, Badge, Button, Card, Group, List, Loader, Stack, Text } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { errorMessage } from '../api/client';
import { useApplyFile } from '../api/jobs';
import { FLAG_LABELS, usePlan } from '../api/policy';
import { formatBytes } from '../format';

/** What ReelHaven would do with one file. */
export function PlanView({ fileId }: { fileId: number }) {
  const plan = usePlan(fileId);
  const apply = useApplyFile();
  if (plan.isPending) return <Loader size="sm" />;
  if (plan.isError || !plan.data) return null;
  const p = plan.data;
  const remuxSaved = (p.removed_bytes ?? 0) + (p.audio_saved_bytes ?? 0);
  return (
    <Card withBorder>
      <Stack gap="xs">
        <Group gap="xs">
          <Text size="sm" fw={500}>
            What ReelHaven would do
          </Text>
          <Badge color={p.action === 'encode' ? 'violet' : p.action === 'remux' ? 'blue' : 'gray'}>
            {p.action === 'encode' ? 'Re-encode' : p.action === 'remux' ? 'Remux' : 'Nothing'}
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
        {p.video && p.video.decision === 'keep' && (
          <Text size="xs" c="dimmed">
            Video kept as it is: {p.video.reason}
          </Text>
        )}
        {p.action === 'encode' && p.video?.bytes_after_estimate != null && (
          <Text size="xs" c="dimmed">
            Estimated {formatBytes(p.video.bytes_before)} →{' '}
            {formatBytes(p.video.bytes_after_estimate)} ({p.video.savings_percent}% smaller). The
            real result is checked after encoding.
          </Text>
        )}
        {p.action === 'remux' && p.removed_bytes !== null && remuxSaved > 0 && (
          <Text size="xs" c="dimmed">
            Saves about {formatBytes(remuxSaved)}.
          </Text>
        )}
        {(p.action === 'remux' || p.action === 'encode') && (
          <Group>
            <Button
              size="xs"
              loading={apply.isPending}
              onClick={() =>
                apply.mutate(fileId, {
                  onSuccess: () => notifications.show({ message: 'Queued. See the Jobs page.' }),
                })
              }
            >
              Apply to this file
            </Button>
            {apply.isError && (
              <Text size="sm" c="red">
                {errorMessage(apply.error)}
              </Text>
            )}
          </Group>
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
