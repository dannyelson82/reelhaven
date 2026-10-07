import { Anchor, Badge, Card, Code, Group, List, Stack, Text, Title } from '@mantine/core';
import { Link } from 'react-router';
import { type WebhookLast, useWebhookStatus, webhookUrl } from '../api/webhooks';

const APPS = [
  {
    kind: 'sonarr' as const,
    name: 'Sonarr',
    triggers: 'On Import, On Upgrade, On Rename, On Series Delete, On Episode File Delete',
  },
  {
    kind: 'radarr' as const,
    name: 'Radarr',
    triggers: 'On Import, On Upgrade, On Rename, On Movie Delete, On Movie File Delete',
  },
];

const OUTCOME_COLOR: Record<WebhookLast['outcome'], string> = {
  test: 'teal',
  rescan: 'teal',
  not_watched: 'yellow',
  no_library: 'red',
  ignored: 'gray',
};

/** How to point Sonarr/Radarr's webhooks at ReelHaven, and what arrived last (ADR-0025). */
export function WebhooksCard() {
  const status = useWebhookStatus();
  return (
    <Card withBorder>
      <Stack gap="sm">
        <Title order={4}>Webhooks</Title>
        <Text size="sm" c="dimmed">
          Let Sonarr and Radarr tell ReelHaven the moment they import, upgrade, rename or delete a
          file. Libraries set to Watch or Automatic are then rescanned straight away.
        </Text>
        <List size="sm" type="ordered">
          <List.Item>
            Create an API key on the{' '}
            <Anchor component={Link} to="/settings/security">
              Security
            </Anchor>{' '}
            page if you haven&apos;t yet, and keep it at hand.
          </List.Item>
          <List.Item>
            In Sonarr or Radarr: <b>Settings → Connect → +</b> and choose <b>Webhook</b>. Name it
            ReelHaven.
          </List.Item>
          <List.Item>Tick the triggers listed below, set Method to POST.</List.Item>
          <List.Item>
            Paste the URL below and replace <Code>YOUR_API_KEY</Code> with your key. If Sonarr runs
            on the same server, use the server&apos;s address and port 7171 rather than a reverse
            proxy address.
          </List.Item>
          <List.Item>
            Click <b>Test</b> in Sonarr/Radarr, then <b>Save</b>. The test shows up here.
          </List.Item>
        </List>
        {APPS.map(({ kind, name, triggers }) => {
          const last = status.data?.[kind];
          return (
            <Card key={kind} withBorder padding="sm">
              <Stack gap={4}>
                <Text fw={600}>{name}</Text>
                <Code block>{webhookUrl(kind)}</Code>
                <Text size="xs" c="dimmed">
                  Triggers: {triggers}
                </Text>
                {last ? (
                  <Group gap="xs">
                    <Badge color={OUTCOME_COLOR[last.outcome]} variant="light">
                      {last.event}
                    </Badge>
                    <Text size="xs">
                      {new Date(last.at).toLocaleString()}: {last.message}
                    </Text>
                  </Group>
                ) : (
                  <Text size="xs" c="dimmed">
                    Nothing received yet.
                  </Text>
                )}
              </Stack>
            </Card>
          );
        })}
      </Stack>
    </Card>
  );
}
