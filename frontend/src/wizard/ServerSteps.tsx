// The wizard's once-per-server steps (ADR-0026): hardware, then the apps you use.
import {
  Alert,
  Anchor,
  Badge,
  Button,
  Card,
  Collapse,
  Group,
  Loader,
  Stack,
  Switch,
  Text,
} from '@mantine/core';
import { IconCheck, IconCpu, IconRefresh } from '@tabler/icons-react';
import { useState } from 'react';
import { Link } from 'react-router';
import { errorMessage } from '../api/client';
import { useDetectDevices, useDevices, useSaveDeviceSettings } from '../api/devices';
import { type IntegrationKind, KIND_LABELS, useIntegrations } from '../api/integrations';
import { WebhooksCard } from '../components/WebhooksCard';
import { IntegrationModal } from '../pages/IntegrationsPage';
import { useOnboarding, useSaveOnboarding } from '../api/wizard';
import { canEncode } from './choices';
import type { StepProps } from './LibrarySteps';

const FORMATS: { codec: string; ten_bit: boolean; label: string }[] = [
  { codec: 'hevc', ten_bit: true, label: 'HEVC' },
  { codec: 'av1', ten_bit: true, label: 'AV1' },
  { codec: 'h264', ten_bit: false, label: 'H.264' },
];

function NavButtons({ onBack, next }: { onBack?: () => void; next: React.ReactNode }) {
  return (
    <Group justify="space-between" mt="md">
      {onBack ? (
        <Button variant="default" onClick={onBack}>
          Back
        </Button>
      ) : (
        <span />
      )}
      {next}
    </Group>
  );
}

export function HardwareStep({ onNext, onBack }: StepProps) {
  const devices = useDevices();
  const detect = useDetectDevices();
  const save = useSaveDeviceSettings();
  const data = devices.data;
  if (!data || !data.detected_at) {
    return (
      <Group>
        <Loader size="sm" />
        <Text>Trying a short test encode on every graphics card… this takes up to a minute.</Text>
      </Group>
    );
  }
  const gpus = data.devices.filter((d) => d.kind !== 'cpu');
  const working = gpus.filter((g) => g.results.some((r) => r.ok));
  const ready = canEncode(data.devices, 'hevc', true);
  return (
    <Stack>
      <Text>
        Making video smaller is hard work. A graphics card (GPU) does it many times faster than the
        processor.
      </Text>
      {working.map((gpu) => (
        <Card key={gpu.id} withBorder padding="sm">
          <Group justify="space-between">
            <Group gap="xs">
              <IconCheck color="var(--mantine-color-teal-6)" />
              <Text fw={600}>{gpu.name}</Text>
            </Group>
            <Group gap={4}>
              {FORMATS.filter((f) =>
                gpu.results.some((r) => r.ok && r.codec === f.codec && r.ten_bit === f.ten_bit),
              ).map((f) => (
                <Badge key={f.codec} variant="light" color="teal">
                  {f.label}
                </Badge>
              ))}
            </Group>
          </Group>
        </Card>
      ))}
      {working.length === 0 && (
        <Alert color="yellow" title="No graphics card found">
          <Text size="sm">
            ReelHaven can't use a graphics card yet. The container needs access to it: see{' '}
            <b>Give the container your GPUs</b> in the guide&apos;s Hardware page, restart
            ReelHaven, and click <b>Detect again</b>. Until then you can let the processor do the
            work: it's much slower, but it works.
          </Text>
        </Alert>
      )}
      {working.length === 0 && (
        <Switch
          label="Allow CPU encoding (slow)"
          checked={data.settings.cpu_enabled}
          disabled={save.isPending}
          onChange={(e) => save.mutate({ ...data.settings, cpu_enabled: e.currentTarget.checked })}
          thumbIcon={<IconCpu size={12} />}
        />
      )}
      {save.isError && <Alert color="red">{errorMessage(save.error)}</Alert>}
      <Group>
        <Button
          variant="subtle"
          size="xs"
          leftSection={<IconRefresh size={14} />}
          loading={data.detecting || detect.isPending}
          onClick={() => detect.mutate()}
        >
          Detect again
        </Button>
        <Anchor component={Link} to="/settings/hardware" size="xs">
          Hardware details
        </Anchor>
      </Group>
      {!ready && (
        <Text size="sm" c="dimmed">
          You can carry on: languages can still be tidied, and re-encoding starts once a graphics
          card or CPU encoding is available.
        </Text>
      )}
      <NavButtons onBack={onBack} next={<Button onClick={() => onNext()}>Next</Button>} />
    </Stack>
  );
}

const APPS: { kind: IntegrationKind; why: string }[] = [
  {
    kind: 'sonarr',
    why: 'Knows the original language of every series and tells ReelHaven about new episodes.',
  },
  {
    kind: 'radarr',
    why: 'Knows the original language of every movie and tells ReelHaven about new films.',
  },
  { kind: 'plex', why: 'Refreshes just the folders ReelHaven changed.' },
];

export function AppsStep({ onNext, onBack }: StepProps) {
  const integrations = useIntegrations();
  const onboarding = useOnboarding();
  const saveOnboarding = useSaveOnboarding();
  // Hardware and apps are asked once per server; later runs start at the library.
  const finish = () =>
    onboarding.data
      ? saveOnboarding.mutate(
          { ...onboarding.data, server_steps_done: true },
          { onSuccess: () => onNext() },
        )
      : onNext();
  const [adding, setAdding] = useState<IntegrationKind | null>(null);
  const [webhooks, setWebhooks] = useState(false);
  if (!integrations.data) return <Loader />;
  const connected = (kind: IntegrationKind) => integrations.data.some((i) => i.kind === kind);
  const arr = connected('sonarr') || connected('radarr');
  return (
    <Stack>
      <Text>
        Do you use any of these? Connecting them is optional, but makes ReelHaven smarter. You can
        also do it later on the Integrations page.
      </Text>
      {APPS.map(({ kind, why }) => (
        <Card key={kind} withBorder padding="sm">
          <Group justify="space-between" wrap="nowrap">
            <Stack gap={0}>
              <Text fw={600}>{KIND_LABELS[kind]}</Text>
              <Text size="xs" c="dimmed">
                {why}
              </Text>
            </Stack>
            {connected(kind) ? (
              <Badge color="teal" leftSection={<IconCheck size={12} />}>
                Connected
              </Badge>
            ) : (
              <Button size="xs" variant="light" onClick={() => setAdding(kind)}>
                Add
              </Button>
            )}
          </Group>
        </Card>
      ))}
      {arr && (
        <>
          <Anchor
            component="button"
            size="sm"
            w="fit-content"
            onClick={() => setWebhooks(!webhooks)}
          >
            {webhooks ? 'Hide' : 'Show'} how to get instant new-file notices (optional)
          </Anchor>
          <Collapse expanded={webhooks}>
            <WebhooksCard />
          </Collapse>
        </>
      )}
      {adding && <IntegrationModal existing={null} kind={adding} onClose={() => setAdding(null)} />}
      <NavButtons
        onBack={onBack}
        next={
          <Button loading={saveOnboarding.isPending} onClick={finish}>
            {integrations.data.some((i) => APPS.some((a) => a.kind === i.kind)) ? 'Next' : 'Skip'}
          </Button>
        }
      />
    </Stack>
  );
}
