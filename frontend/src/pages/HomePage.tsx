import { Center, Image, Stack, Text, Title } from '@mantine/core';

export function HomePage() {
  return (
    <Center mih="100vh">
      <Stack align="center" gap="xs">
        <Image src="./favicon.svg" w={96} h={96} alt="" />
        <Title order={1}>ReelHaven</Title>
        <Text c="dimmed">Smaller files. The right language.</Text>
      </Stack>
    </Center>
  );
}
