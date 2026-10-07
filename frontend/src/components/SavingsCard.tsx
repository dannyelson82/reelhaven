// Space saved over the life of the install (ADR-0026), on the Dashboard.
import { BarChart } from '@mantine/charts';
import {
  Anchor,
  Card,
  Group,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Title,
  useComputedColorScheme,
} from '@mantine/core';
import { useState } from 'react';
import { type SavingsPeriod, useSavings } from '../api/stats';
import { formatBytes } from '../format';

function StatTile({
  label,
  value,
  hero = false,
}: {
  label: string;
  value: string;
  hero?: boolean;
}) {
  return (
    <Stack gap={2}>
      <Text size="sm" c="dimmed">
        {label}
      </Text>
      <Text fz={hero ? 40 : 24} fw={700} lh={1.1}>
        {value}
      </Text>
    </Stack>
  );
}

function periodLabel(start: string, view: 'weekly' | 'monthly'): string {
  const [y, m, d] = start.split('-').map(Number);
  const date = new Date(y, m - 1, d);
  return view === 'weekly'
    ? date.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
    : date.toLocaleDateString(undefined, { month: 'short', year: 'numeric' });
}

export function SavingsCard() {
  const savings = useSavings();
  const scheme = useComputedColorScheme('light');
  const [view, setView] = useState<'weekly' | 'monthly'>('weekly');
  const [table, setTable] = useState(false);
  const s = savings.data;
  if (!s) return null;
  if (s.files === 0 && s.total_saved === 0) return null; // nothing to show yet
  const periods: SavingsPeriod[] = s[view];
  const data = periods.map((p) => ({
    period: periodLabel(p.start, view),
    saved: p.saved,
    files: p.files,
  }));
  // Validated steps (dataviz validator): teal 8 on light, teal 7 on dark.
  const color = scheme === 'dark' ? 'teal.7' : 'teal.8';
  return (
    <Card withBorder padding="lg">
      <Stack>
        <Title order={4}>Space saved</Title>
        <SimpleGrid cols={{ base: 2, sm: 4 }}>
          <StatTile label="Since you installed ReelHaven" value={formatBytes(s.total_saved)} hero />
          <StatTile label="This week" value={formatBytes(s.this_week)} />
          <StatTile label="This month" value={formatBytes(s.this_month)} />
          <StatTile label="Files made smaller" value={s.files.toLocaleString()} />
        </SimpleGrid>
        <Group justify="space-between">
          <SegmentedControl
            size="xs"
            value={view}
            onChange={(v) => setView(v as 'weekly' | 'monthly')}
            data={[
              { value: 'weekly', label: 'Weekly' },
              { value: 'monthly', label: 'Monthly' },
            ]}
          />
          <Anchor component="button" size="sm" onClick={() => setTable(!table)}>
            {table ? 'Show as chart' : 'Show as table'}
          </Anchor>
        </Group>
        {table ? (
          <Table striped>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{view === 'weekly' ? 'Week of' : 'Month'}</Table.Th>
                <Table.Th ta="right">Space saved</Table.Th>
                <Table.Th ta="right">Files</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {data.map((row) => (
                <Table.Tr key={row.period}>
                  <Table.Td>{row.period}</Table.Td>
                  <Table.Td ta="right">{formatBytes(row.saved)}</Table.Td>
                  <Table.Td ta="right">{row.files}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        ) : (
          <BarChart
            h={220}
            data={data}
            dataKey="period"
            series={[{ name: 'saved', label: 'Space saved', color }]}
            valueFormatter={(value) => formatBytes(value)}
            gridAxis="x"
            tickLine="none"
            maxBarWidth={24}
            barProps={{ radius: [4, 4, 0, 0] }}
            aria-label={`Space saved per ${view === 'weekly' ? 'week' : 'month'}`}
          />
        )}
        {s.libraries.length > 1 && (
          <Stack gap={4}>
            <Text size="sm" fw={700} mt="xs">
              By library
            </Text>
            {s.libraries.map((lib) => (
              <Group key={lib.library_id} justify="space-between">
                <Text size="sm">{lib.name}</Text>
                <Text size="sm" c="dimmed">
                  {formatBytes(lib.saved)} · {lib.files.toLocaleString()}{' '}
                  {lib.files === 1 ? 'file' : 'files'}
                </Text>
              </Group>
            ))}
          </Stack>
        )}
      </Stack>
    </Card>
  );
}
