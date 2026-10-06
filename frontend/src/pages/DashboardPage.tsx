import { Stack, Text, Title } from '@mantine/core';

export function DashboardPage() {
  return (
    <Stack>
      <Title order={2}>Dashboard</Title>
      <Text c="dimmed">
        Nothing to show yet. Libraries arrive in the next phase; for now you can review your
        security settings.
      </Text>
    </Stack>
  );
}
