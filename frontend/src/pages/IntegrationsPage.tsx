import {
  ActionIcon,
  Alert,
  Badge,
  Button,
  Card,
  Code,
  Group,
  Loader,
  Modal,
  PasswordInput,
  Stack,
  Switch,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import { IconCheck, IconPlus, IconTrash, IconX } from '@tabler/icons-react';
import { useState } from 'react';
import { errorMessage } from '../api/client';
import { WebhooksCard } from '../components/WebhooksCard';
import {
  type Integration,
  type IntegrationForm,
  type IntegrationKind,
  KIND_LABELS,
  useCreateIntegration,
  useDeleteIntegration,
  useIntegrations,
  useTestIntegration,
  useUpdateIntegration,
} from '../api/integrations';

const HELP: Record<IntegrationKind, string> = {
  sonarr:
    'Gives the original language of each series, and rescans series ReelHaven changes. API key: Sonarr → Settings → General → Security.',
  radarr:
    'Gives the original language of each movie, and rescans movies ReelHaven changes. API key: Radarr → Settings → General → Security.',
  tmdb: "Fallback for files Sonarr/Radarr don't manage. Free key: themoviedb.org → Settings → API.",
  plex: 'Scans just the folders ReelHaven changes. Token: in Plex Web open any movie → ⋯ → Get Info → View XML; the address ends with X-Plex-Token=….',
};

export function IntegrationsPage() {
  const integrations = useIntegrations();
  const [editing, setEditing] = useState<Integration | IntegrationKind | null>(null);

  return (
    <Stack maw={860}>
      <Group justify="space-between">
        <Title order={2}>Integrations</Title>
        <Group gap="xs">
          {(Object.keys(KIND_LABELS) as IntegrationKind[]).map((kind) => (
            <Button
              key={kind}
              variant={kind === 'tmdb' ? 'default' : 'filled'}
              leftSection={<IconPlus size={16} />}
              onClick={() => setEditing(kind)}
            >
              Add {KIND_LABELS[kind]}
            </Button>
          ))}
        </Group>
      </Group>
      <Text size="sm" c="dimmed">
        ReelHaven asks these services what language each title was originally made in. API keys are
        stored encrypted and are never shown again after saving.
      </Text>
      {integrations.isPending && <Loader />}
      {integrations.isError && <Alert color="red">{errorMessage(integrations.error)}</Alert>}
      {integrations.data?.length === 0 && (
        <Card withBorder>
          <Text c="dimmed">No integrations yet. Add Sonarr and Radarr if you use them.</Text>
        </Card>
      )}
      {integrations.data?.map((integration) => (
        <Card key={integration.id} withBorder>
          <Group justify="space-between">
            <Stack gap={2}>
              <Group gap="xs">
                <Text fw={600}>{integration.name}</Text>
                <Badge variant="light">{KIND_LABELS[integration.kind]}</Badge>
                {!integration.enabled && <Badge color="gray">Off</Badge>}
              </Group>
              <Code>{integration.base_url}</Code>
              <Text size="xs" c="dimmed">
                {integration.kind === 'plex' ? 'Token' : 'API key'}{' '}
                {integration.api_key_hint || 'missing (re-enter it)'}
                {integration.path_mappings.length > 0 &&
                  ` · ${integration.path_mappings.length} path mapping(s)`}
              </Text>
              {integration.last_notify && (
                <Text size="xs" c={integration.last_notify.ok ? 'dimmed' : 'red'}>
                  Last update sent {new Date(integration.last_notify.at).toLocaleString()}:{' '}
                  {integration.last_notify.message}
                </Text>
              )}
            </Stack>
            <Button variant="default" onClick={() => setEditing(integration)}>
              Edit
            </Button>
          </Group>
        </Card>
      ))}
      <WebhooksCard />
      {editing !== null && (
        <IntegrationModal
          existing={typeof editing === 'string' ? null : editing}
          kind={typeof editing === 'string' ? editing : editing.kind}
          onClose={() => setEditing(null)}
        />
      )}
    </Stack>
  );
}

export function IntegrationModal({
  existing,
  kind,
  onClose,
}: {
  existing: Integration | null;
  kind: IntegrationKind;
  onClose: () => void;
}) {
  const create = useCreateIntegration();
  const update = useUpdateIntegration();
  const remove = useDeleteIntegration();
  const test = useTestIntegration();
  const isTmdb = kind === 'tmdb';
  const form = useForm<IntegrationForm>({
    initialValues: {
      kind,
      name: existing?.name ?? KIND_LABELS[kind],
      base_url: existing?.base_url ?? '',
      api_key: '',
      verify_tls: existing?.verify_tls ?? true,
      path_mappings: existing?.path_mappings ?? [],
      enabled: existing?.enabled ?? true,
    },
    validate: {
      name: (v) => (v.trim() ? null : 'Give it a name'),
      base_url: (v) =>
        isTmdb || /^https?:\/\/.+/.test(v.trim())
          ? null
          : 'Use a full address like http://192.168.1.10:8989',
      api_key: (v) => (existing || v.trim() ? null : 'Enter the API key'),
      path_mappings: {
        remote: (v) => (v.startsWith('/') || /^[A-Za-z]:\\/.test(v) ? null : 'Start with /'),
        local: (v) => (v.startsWith('/') ? null : 'Start with /'),
      },
    },
  });
  const saving = create.isPending || update.isPending;
  const saveError = create.error ?? update.error ?? remove.error;

  const save = form.onSubmit((values) => {
    const done = () => {
      notifications.show({ message: `${values.name} saved.` });
      onClose();
    };
    if (existing) update.mutate({ ...values, id: existing.id }, { onSuccess: done });
    else create.mutate(values, { onSuccess: done });
  });

  return (
    <Modal
      opened
      onClose={onClose}
      title={`${existing ? 'Edit' : 'Add'} ${KIND_LABELS[kind]}`}
      size="lg"
    >
      <form onSubmit={save}>
        <Stack>
          <Text size="sm" c="dimmed">
            {HELP[kind]}
          </Text>
          <TextInput label="Name" {...form.getInputProps('name')} />
          {!isTmdb && (
            <TextInput
              label="Address"
              placeholder={
                kind === 'plex' ? 'http://192.168.1.10:32400' : 'http://192.168.1.10:8989'
              }
              description="Include the URL base if you set one, e.g. http://host:8989/sonarr"
              {...form.getInputProps('base_url')}
            />
          )}
          <PasswordInput
            label={
              isTmdb ? 'API key or read access token' : kind === 'plex' ? 'Plex token' : 'API key'
            }
            placeholder={existing ? `Saved (${existing.api_key_hint}); leave empty to keep it` : ''}
            autoComplete="off"
            {...form.getInputProps('api_key')}
          />
          {!isTmdb && (
            <Switch
              label="Check the HTTPS certificate"
              description="Turn off only for a self-signed certificate on your own network."
              {...form.getInputProps('verify_tls', { type: 'checkbox' })}
            />
          )}
          {!isTmdb && (
            <Stack gap={4}>
              <Text size="sm" fw={500}>
                Path mappings
              </Text>
              <Text size="xs" c="dimmed">
                Only needed if {KIND_LABELS[kind]} sees your files at a different path, e.g. it uses
                /tv where ReelHaven uses /media/TV.
              </Text>
              {form.values.path_mappings.map((_, i) => (
                <Group key={i} gap="xs" align="flex-start">
                  <TextInput
                    placeholder={`${KIND_LABELS[kind]} path, e.g. /tv`}
                    style={{ flex: 1 }}
                    {...form.getInputProps(`path_mappings.${i}.remote`)}
                  />
                  <Text mt={6}>→</Text>
                  <TextInput
                    placeholder="ReelHaven path, e.g. /media/TV"
                    style={{ flex: 1 }}
                    {...form.getInputProps(`path_mappings.${i}.local`)}
                  />
                  <ActionIcon
                    variant="subtle"
                    color="red"
                    mt={4}
                    aria-label="Remove mapping"
                    onClick={() => form.removeListItem('path_mappings', i)}
                  >
                    <IconTrash size={16} />
                  </ActionIcon>
                </Group>
              ))}
              <Group>
                <Button
                  variant="subtle"
                  size="xs"
                  onClick={() => form.insertListItem('path_mappings', { remote: '', local: '' })}
                >
                  Add mapping
                </Button>
              </Group>
            </Stack>
          )}
          <Switch label="Enabled" {...form.getInputProps('enabled', { type: 'checkbox' })} />

          {test.data && (
            <Alert
              color={test.data.ok ? 'teal' : 'red'}
              icon={test.data.ok ? <IconCheck /> : <IconX />}
            >
              {test.data.ok
                ? `Connected to ${test.data.app} ${test.data.version ?? ''}`.trim()
                : test.data.message}
            </Alert>
          )}
          {test.isError && <Alert color="red">{errorMessage(test.error)}</Alert>}
          {saveError && <Alert color="red">{errorMessage(saveError)}</Alert>}

          <Group justify="space-between">
            <Group gap="xs">
              <Button
                variant="default"
                loading={test.isPending}
                onClick={() =>
                  test.mutate({
                    kind,
                    base_url: form.values.base_url,
                    api_key: form.values.api_key || undefined,
                    verify_tls: form.values.verify_tls,
                    id: existing?.id,
                  })
                }
              >
                Test connection
              </Button>
              {existing && (
                <Button
                  variant="subtle"
                  color="red"
                  loading={remove.isPending}
                  onClick={() => remove.mutate(existing.id, { onSuccess: onClose })}
                >
                  Remove
                </Button>
              )}
            </Group>
            <Button type="submit" loading={saving}>
              Save
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
