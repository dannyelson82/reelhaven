// Per-device performance and trends (ADR-0032).
import { BarChart } from '@mantine/charts';
import {
  Alert,
  Card,
  Group,
  Loader,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Text,
  Title,
  useComputedColorScheme,
} from '@mantine/core';
import { useState } from 'react';
import { errorMessage } from '../api/client';
import { useDeviceName } from '../api/devices';
import { type DeviceStats, usePerformance } from '../api/stats';
import { SavingsCard } from '../components/SavingsCard';
import { formatBytes } from '../format';

const PERIODS = [
  { value: '7', label: '7 days' },
  { value: '30', label: '30 days' },
  { value: '90', label: '90 days' },
  { value: '0', label: 'All time' },
];

export function StatsPage() {
  const [days, setDays] = useState('30');
  const performance = usePerformance(Number(days));
  const dark = useComputedColorScheme('light') === 'dark';

  return (
    <Stack>
      <Title order={2}>Stats</Title>
      <Group justify="space-between">
        <Title order={4}>Graphics cards and CPU</Title>
        <SegmentedControl size="xs" value={days} onChange={setDays} data={PERIODS} />
      </Group>
      {performance.isPending && <Loader />}
      {performance.isError && <Alert color="red">{errorMessage(performance.error)}</Alert>}
      {performance.data && performance.data.devices.length === 0 && (
        <Text c="dimmed">No re-encodes finished in this period yet.</Text>
      )}
      <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
        {performance.data?.devices.map((d) => (
          <DeviceCard key={d.device} stats={d} />
        ))}
      </SimpleGrid>
      {performance.data && (
        <Card withBorder>
          <Stack gap="xs">
            <Title order={4}>Jobs per day, last 30 days</Title>
            <BarChart
              h={220}
              data={performance.data.daily.map((d) => ({ ...d, day: d.day.slice(5) }))}
              dataKey="day"
              type="stacked"
              series={[
                { name: 'encoded', label: 'Re-encoded', color: dark ? 'teal.4' : 'teal.6' },
                { name: 'remuxed', label: 'Tracks changed', color: dark ? 'blue.4' : 'blue.6' },
                { name: 'failed', label: 'Failed', color: dark ? 'red.4' : 'red.6' },
              ]}
              withLegend
              gridAxis="x"
              tickLine="none"
              maxBarWidth={16}
              aria-label="Jobs per day"
            />
          </Stack>
        </Card>
      )}
      <SavingsCard />
    </Stack>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <Stack gap={0}>
      <Text size="xs" c="dimmed" tt="uppercase" fw={600}>
        {label}
      </Text>
      <Text fw={600}>{value}</Text>
    </Stack>
  );
}

function DeviceCard({ stats: d }: { stats: DeviceStats }) {
  const name = useDeviceName()(d.device) ?? d.device;
  return (
    <Card withBorder>
      <Stack gap="sm">
        <Text fw={700}>{name}</Text>
        <SimpleGrid cols={2} spacing="xs">
          <Fact label="Files" value={d.files.toLocaleString()} />
          <Fact label="Saved" value={formatBytes(d.saved)} />
          <Fact label="Speed" value={d.speed !== null ? `${d.speed.toFixed(1)}× real time` : '–'} />
          <Fact label="Average" value={d.fps !== null ? `${d.fps.toFixed(0)} fps` : '–'} />
          <Fact
            label="Video"
            value={`${d.video_hours.toFixed(1)} h in ${d.work_hours.toFixed(1)} h`}
          />
          <Fact
            label="Decoded on GPU"
            value={d.gpu_decoded !== null ? `${Math.round(d.gpu_decoded * 100)}%` : '–'}
          />
        </SimpleGrid>
        {d.failed > 0 && (
          <Text size="xs" c="red">
            {d.failed} failed
          </Text>
        )}
      </Stack>
    </Card>
  );
}
