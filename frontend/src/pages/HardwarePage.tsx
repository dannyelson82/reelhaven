import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Loader,
  NumberInput,
  Stack,
  Switch,
  Table,
  Text,
  Title,
  Tooltip,
} from '@mantine/core';
import { IconCheck, IconCpu, IconRefresh, IconX } from '@tabler/icons-react';
import { errorMessage } from '../api/client';
import {
  type DeviceInfo,
  type DeviceSettings,
  useDetectDevices,
  useDevices,
  useSaveDeviceSettings,
} from '../api/devices';

const ROWS: { codec: 'hevc' | 'av1' | 'h264'; ten_bit: boolean; label: string }[] = [
  { codec: 'hevc', ten_bit: false, label: 'HEVC 8-bit' },
  { codec: 'hevc', ten_bit: true, label: 'HEVC 10-bit' },
  { codec: 'av1', ten_bit: false, label: 'AV1 8-bit' },
  { codec: 'av1', ten_bit: true, label: 'AV1 10-bit' },
  { codec: 'h264', ten_bit: false, label: 'H.264' },
];

export function HardwarePage() {
  const devices = useDevices();
  const detect = useDetectDevices();
  const save = useSaveDeviceSettings();
  const data = devices.data;
  const gpus = data?.devices.filter((d) => d.kind !== 'cpu') ?? [];

  const update = (change: (s: DeviceSettings) => DeviceSettings) => {
    if (data) save.mutate(change(structuredClone(data.settings)));
  };

  return (
    <Stack maw={960}>
      <Group justify="space-between">
        <Title order={2}>Hardware</Title>
        <Button
          variant="default"
          leftSection={<IconRefresh size={16} />}
          loading={data?.detecting || detect.isPending}
          onClick={() => detect.mutate()}
        >
          Detect again
        </Button>
      </Group>
      <Text size="sm" c="dimmed">
        ReelHaven tries a one-second test encode on every device for every format, so this shows
        what really works inside the container.
      </Text>
      {devices.isPending && <Loader />}
      {devices.isError && <Alert color="red">{errorMessage(devices.error)}</Alert>}
      {data && !data.detected_at && (
        <Alert color="blue" icon={<Loader size="xs" />}>
          Testing your devices… this takes up to a minute.
        </Alert>
      )}
      {data?.detected_at && gpus.length === 0 && (
        <Alert color="yellow" title="No GPU found">
          <Text size="sm">
            For NVIDIA, add <code>--runtime=nvidia</code> to Extra Parameters and set{' '}
            <code>NVIDIA_VISIBLE_DEVICES</code> in the container settings. For Intel or AMD, add{' '}
            <code>/dev/dri</code> as a Device. Then restart ReelHaven and click “Detect again”.
          </Text>
        </Alert>
      )}
      {save.isError && <Alert color="red">{errorMessage(save.error)}</Alert>}
      {data?.cpu_cores_available !== undefined && (
        <CpuLimit
          available={data.cpu_cores_available}
          value={data.settings.cpu_cores ?? null}
          saving={save.isPending}
          onChange={(cores) => update((s) => ({ ...s, cpu_cores: cores }))}
        />
      )}
      {data?.devices.map((device) => (
        <DeviceCard
          key={device.id}
          device={device}
          saving={save.isPending}
          onToggle={(enabled) =>
            update((s) =>
              device.kind === 'cpu'
                ? { ...s, cpu_enabled: enabled }
                : {
                    ...s,
                    devices: {
                      ...s.devices,
                      [device.id]: { concurrency: device.concurrency, enabled },
                    },
                  },
            )
          }
          onConcurrency={(concurrency) =>
            update((s) =>
              device.kind === 'cpu'
                ? { ...s, cpu_concurrency: concurrency }
                : {
                    ...s,
                    devices: {
                      ...s.devices,
                      [device.id]: { enabled: device.enabled, concurrency },
                    },
                  },
            )
          }
        />
      ))}
    </Stack>
  );
}

/** CPU limiter: how many cores ReelHaven's processes may use (always at low priority). */
function CpuLimit({
  available,
  value,
  saving,
  onChange,
}: {
  available: number;
  value: number | null;
  saving: boolean;
  onChange: (cores: number | null) => void;
}) {
  const limited = value !== null && value < available;
  return (
    <Card withBorder>
      <Stack gap="xs">
        <Group gap="xs">
          <IconCpu size={18} />
          <Text fw={600}>CPU limit</Text>
        </Group>
        <Text size="sm" c="dimmed">
          Everything ReelHaven runs on the CPU (CPU encodes, files a graphics card can&apos;t
          decode, audio conversion, quality checks, reading files) always runs at low priority, so
          Plex and your other containers come first. You can also cap how many cores it may use.
        </Text>
        <Group gap="md" align="flex-end">
          <Switch
            label="Limit CPU cores"
            checked={limited}
            disabled={saving || available < 2}
            onChange={(e) =>
              onChange(e.currentTarget.checked ? Math.max(1, Math.floor(available / 2)) : null)
            }
          />
          {limited && (
            <NumberInput
              label={`Cores to use (of ${available})`}
              min={1}
              max={available - 1}
              value={value}
              w={180}
              disabled={saving}
              onChange={(v) => typeof v === 'number' && v >= 1 && onChange(v)}
            />
          )}
        </Group>
        <Text size="xs" c="dimmed">
          {limited
            ? `ReelHaven uses at most ${value} of ${available} cores; jobs already running keep their cores until they finish.`
            : `ReelHaven may use all ${available} cores when nothing else needs them.`}
        </Text>
      </Stack>
    </Card>
  );
}

function DeviceCard({
  device,
  saving,
  onToggle,
  onConcurrency,
}: {
  device: DeviceInfo;
  saving: boolean;
  onToggle: (enabled: boolean) => void;
  onConcurrency: (value: number) => void;
}) {
  const isCpu = device.kind === 'cpu';
  return (
    <Card withBorder>
      <Stack gap="sm">
        <Group justify="space-between">
          <Group gap="xs">
            {isCpu && <IconCpu size={18} />}
            <Text fw={600}>{device.name}</Text>
            <Badge variant="light">{device.kind.toUpperCase()}</Badge>
          </Group>
          <Group gap="md">
            <NumberInput
              label="At the same time"
              size="xs"
              min={1}
              max={isCpu ? 4 : 8}
              w={130}
              value={device.concurrency}
              disabled={saving}
              onChange={(v) => typeof v === 'number' && v >= 1 && onConcurrency(v)}
            />
            <Switch
              label={isCpu ? 'Allow CPU encoding (slow)' : 'Use for encoding'}
              checked={device.enabled}
              disabled={saving}
              onChange={(e) => onToggle(e.currentTarget.checked)}
            />
          </Group>
        </Group>
        <Table withRowBorders={false} verticalSpacing={4}>
          <Table.Tbody>
            {ROWS.map((row) => {
              const result = device.results.find(
                (r) => r.codec === row.codec && r.ten_bit === row.ten_bit,
              );
              return (
                <Table.Tr key={row.label}>
                  <Table.Td w={140}>
                    <Text size="sm">{row.label}</Text>
                  </Table.Td>
                  <Table.Td>
                    {!result ? (
                      <Text size="sm" c="dimmed">
                        –
                      </Text>
                    ) : result.ok ? (
                      <Group gap={4}>
                        <IconCheck size={16} color="var(--mantine-color-teal-6)" />
                        <Text size="sm" c="dimmed">
                          {result.encoder}
                        </Text>
                      </Group>
                    ) : (
                      <Tooltip label={result.error ?? 'failed'} multiline w={400}>
                        <Group gap={4}>
                          <IconX size={16} color="var(--mantine-color-red-6)" />
                          <Text size="sm" c="dimmed">
                            not supported
                          </Text>
                        </Group>
                      </Tooltip>
                    )}
                  </Table.Td>
                </Table.Tr>
              );
            })}
          </Table.Tbody>
        </Table>
      </Stack>
    </Card>
  );
}
