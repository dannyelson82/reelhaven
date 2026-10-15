import { Alert, Button, Card, Group, Stack, Switch, Text, Title } from '@mantine/core';
import { IconDownload } from '@tabler/icons-react';
import { errorMessage } from '../api/client';
import {
  FAILURE_REPORT_URL,
  useDeveloperSettings,
  useSaveDeveloperSettings,
} from '../api/developer';

export function DeveloperPage() {
  const settings = useDeveloperSettings();
  const save = useSaveDeveloperSettings();
  const enabled = settings.data?.enabled ?? false;

  return (
    <Stack maw={720}>
      <Title order={2}>Developer options</Title>
      <Card withBorder>
        <Stack>
          <Switch
            label="Developer options"
            description="Shows buttons that download reports about failed jobs and files waiting for review, to send when asking for help."
            checked={enabled}
            disabled={settings.isPending || save.isPending}
            onChange={(e) => save.mutate({ enabled: e.currentTarget.checked })}
          />
          {save.isError && <Alert color="red">{errorMessage(save.error)}</Alert>}
          {enabled && (
            <>
              <Text size="sm" c="dimmed">
                Reports leave out passwords and API keys but include file and folder names.
              </Text>
              <Group>
                <Button
                  component="a"
                  href={FAILURE_REPORT_URL}
                  download
                  variant="default"
                  leftSection={<IconDownload size={16} />}
                >
                  Download failure report
                </Button>
              </Group>
            </>
          )}
        </Stack>
      </Card>
    </Stack>
  );
}
