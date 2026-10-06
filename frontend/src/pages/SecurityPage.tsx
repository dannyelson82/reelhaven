import {
  Alert,
  Button,
  Card,
  Code,
  CopyButton,
  Group,
  Loader,
  Modal,
  NumberInput,
  PasswordInput,
  Stack,
  Switch,
  Text,
  Textarea,
  Title,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import { IconAlertTriangle } from '@tabler/icons-react';
import { useState } from 'react';
import {
  type SecurityView,
  useChangePassword,
  useRotateApiKey,
  useSecurity,
  useUpdateSecurity,
} from '../api/auth';
import { errorMessage } from '../api/client';
import { MIN_PASSWORD } from './SetupPage';

export function SecurityPage() {
  const security = useSecurity();
  if (security.isPending) return <Loader />;
  if (security.isError) return <Alert color="red">{errorMessage(security.error)}</Alert>;
  return (
    <Stack maw={720}>
      <Title order={2}>Security</Title>
      <PasswordCard />
      <AccessCard view={security.data} />
      <ApiKeyCard view={security.data} />
    </Stack>
  );
}

function PasswordCard() {
  const change = useChangePassword();
  const form = useForm({
    initialValues: { current: '', next: '', confirm: '' },
    validate: {
      current: (v) => (v ? null : 'Enter your current password'),
      next: (v) => (v.length >= MIN_PASSWORD ? null : `Use at least ${MIN_PASSWORD} characters`),
      confirm: (v, values) => (v === values.next ? null : 'Passwords do not match'),
    },
  });
  return (
    <Card withBorder>
      <form
        onSubmit={form.onSubmit(({ current, next }) =>
          change.mutate(
            { current_password: current, new_password: next },
            {
              onSuccess: () => {
                form.reset();
                notifications.show({
                  message: 'Password changed. Other devices have been logged out.',
                });
              },
            },
          ),
        )}
      >
        <Stack>
          <Title order={4}>Password</Title>
          <PasswordInput
            label="Current password"
            autoComplete="current-password"
            {...form.getInputProps('current')}
          />
          <PasswordInput
            label="New password"
            autoComplete="new-password"
            {...form.getInputProps('next')}
          />
          <PasswordInput
            label="Confirm new password"
            autoComplete="new-password"
            {...form.getInputProps('confirm')}
          />
          {change.isError && <Alert color="red">{errorMessage(change.error)}</Alert>}
          <Group>
            <Button type="submit" loading={change.isPending}>
              Change password
            </Button>
          </Group>
        </Stack>
      </form>
    </Card>
  );
}

function AccessCard({ view }: { view: SecurityView }) {
  const update = useUpdateSecurity();
  const form = useForm({
    initialValues: {
      local_bypass: view.local_bypass,
      trusted_proxies: view.trusted_proxies.join('\n'),
      session_idle_days: view.session_idle_days,
    },
  });
  const save = form.onSubmit((values) =>
    update.mutate(
      {
        local_bypass: values.local_bypass,
        trusted_proxies: values.trusted_proxies
          .split(/[\s,]+/)
          .map((s) => s.trim())
          .filter(Boolean),
        session_idle_days: Number(values.session_idle_days),
      },
      {
        onSuccess: (saved) => {
          form.setValues({ ...values, trusted_proxies: saved.trusted_proxies.join('\n') });
          form.resetDirty();
          notifications.show({ message: 'Security settings saved.' });
        },
      },
    ),
  );

  return (
    <Card withBorder>
      <form onSubmit={save}>
        <Stack>
          <Title order={4}>Access</Title>
          {view.gateway_warning && (
            <Alert
              color="yellow"
              icon={<IconAlertTriangle />}
              title="Some requests can't be checked"
            >
              Requests are arriving from the Docker network gateway, so ReelHaven can't tell which
              device sent them. Those requests always have to log in, even from your home network.
            </Alert>
          )}
          <Switch
            label="Don't require login on my local network"
            description="Devices on private addresses (192.168.x.x, 10.x.x.x, …) skip the login page."
            {...form.getInputProps('local_bypass', { type: 'checkbox' })}
          />
          {form.values.local_bypass && (
            <Alert color="orange" icon={<IconAlertTriangle />}>
              If you reach ReelHaven from the internet through a reverse proxy on your network, add
              the proxy below. Otherwise everyone coming through it would skip the login.
            </Alert>
          )}
          <Text size="sm">
            Your address as ReelHaven sees it: <Code>{view.client_ip ?? 'unknown'}</Code>{' '}
            {view.bypass_applies_to_you ? '(local network)' : '(not local)'}
          </Text>
          <Textarea
            label="Trusted reverse proxies"
            description="One IP address or range per line, e.g. 192.168.1.50. Only these may tell ReelHaven the real client address."
            autosize
            minRows={2}
            {...form.getInputProps('trusted_proxies')}
          />
          <NumberInput
            label="Log out after this many days of inactivity"
            min={1}
            max={365}
            w={260}
            {...form.getInputProps('session_idle_days')}
          />
          {update.isError && <Alert color="red">{errorMessage(update.error)}</Alert>}
          <Group>
            <Button type="submit" loading={update.isPending} disabled={!form.isDirty()}>
              Save
            </Button>
          </Group>
        </Stack>
      </form>
    </Card>
  );
}

function ApiKeyCard({ view }: { view: SecurityView }) {
  const rotate = useRotateApiKey();
  const [newKey, setNewKey] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

  const generate = () =>
    rotate.mutate(undefined, {
      onSuccess: (result) => {
        setConfirming(false);
        setNewKey(result.api_key);
      },
    });

  return (
    <Card withBorder>
      <Stack>
        <Title order={4}>API key</Title>
        <Text size="sm" c="dimmed">
          For Sonarr/Radarr webhooks and scripts. It can't change security settings.
        </Text>
        {view.api_key ? (
          <Text size="sm">
            Current key starts with <Code>{view.api_key.prefix}…</Code>, created{' '}
            {new Date(view.api_key.created_at).toLocaleString()}.
          </Text>
        ) : (
          <Text size="sm">No API key yet.</Text>
        )}
        {rotate.isError && <Alert color="red">{errorMessage(rotate.error)}</Alert>}
        <Group>
          <Button
            variant="light"
            loading={rotate.isPending}
            onClick={() => (view.api_key ? setConfirming(true) : generate())}
          >
            {view.api_key ? 'Replace API key' : 'Create API key'}
          </Button>
        </Group>
      </Stack>

      <Modal opened={confirming} onClose={() => setConfirming(false)} title="Replace API key?">
        <Stack>
          <Text size="sm">
            The current key stops working immediately. Anything using it will need the new one.
          </Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setConfirming(false)}>
              Cancel
            </Button>
            <Button color="red" loading={rotate.isPending} onClick={generate}>
              Replace
            </Button>
          </Group>
        </Stack>
      </Modal>

      <Modal
        opened={newKey !== null}
        onClose={() => setNewKey(null)}
        title="Your new API key"
        closeOnClickOutside={false}
      >
        <Stack>
          <Alert color="yellow">Copy it now. For your safety it won't be shown again.</Alert>
          <Code block>{newKey}</Code>
          <Group justify="flex-end">
            <CopyButton value={newKey ?? ''}>
              {({ copied, copy }) => (
                <Button variant="light" onClick={copy}>
                  {copied ? 'Copied' : 'Copy'}
                </Button>
              )}
            </CopyButton>
            <Button onClick={() => setNewKey(null)}>Done</Button>
          </Group>
        </Stack>
      </Modal>
    </Card>
  );
}
