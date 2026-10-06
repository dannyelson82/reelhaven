import { Stack, Text, Title } from '@mantine/core';

export function DashboardPage() {
  return (
    <Stack>
      <Title order={2}>Dashboard</Title>
      <Text c="dimmed">
        Nothing to show yet. Start by adding your libraries on the Libraries page.
      </Text>
    </Stack>
  );
}
