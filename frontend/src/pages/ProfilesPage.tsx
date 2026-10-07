import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Loader,
  Modal,
  SegmentedControl,
  Select,
  Slider,
  Stack,
  Switch,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import { useState } from 'react';
import { errorMessage } from '../api/client';
import {
  CODEC_LABELS,
  type Profile,
  type ProfileSettings,
  describe,
  useDeleteProfile,
  useProfiles,
  useSaveProfile,
} from '../api/profiles';

export function ProfilesPage() {
  const profiles = useProfiles();
  const [editing, setEditing] = useState<{
    id?: number;
    name: string;
    settings: ProfileSettings;
  } | null>(null);

  return (
    <Stack maw={860}>
      <Title order={2}>Compression profiles</Title>
      <Text size="sm" c="dimmed">
        A profile decides how video is re-encoded. Pick one per library on the library page; a
        library without a profile only gets the language changes. Built-in profiles can be copied
        and adjusted.
      </Text>
      {profiles.isPending && <Loader />}
      {profiles.isError && <Alert color="red">{errorMessage(profiles.error)}</Alert>}
      {profiles.data?.map((p) => (
        <Card key={p.id} withBorder>
          <Group justify="space-between" wrap="nowrap">
            <Stack gap={2}>
              <Group gap="xs">
                <Text fw={600}>{p.name}</Text>
                {p.builtin && <Badge variant="light">Built-in</Badge>}
              </Group>
              <Text size="sm" c="dimmed">
                {describe(p.settings)}
              </Text>
              {p.used_by.length > 0 && <Text size="xs">Used by: {p.used_by.join(', ')}</Text>}
            </Stack>
            <Group gap="xs" wrap="nowrap">
              <Button
                variant="default"
                size="xs"
                onClick={() => setEditing({ name: `${p.name} (copy)`, settings: p.settings })}
              >
                Copy
              </Button>
              {!p.builtin && (
                <Button
                  size="xs"
                  variant="light"
                  onClick={() => setEditing({ id: p.id, name: p.name, settings: p.settings })}
                >
                  Edit
                </Button>
              )}
            </Group>
          </Group>
        </Card>
      ))}
      {editing && (
        <ProfileModal
          initial={editing}
          existing={profiles.data?.find((p) => p.id === editing.id)}
          onClose={() => setEditing(null)}
        />
      )}
    </Stack>
  );
}

const QUALITY_MARKS = [
  { value: 1, label: 'Smallest' },
  { value: 4, label: 'Small' },
  { value: 6, label: 'Balanced' },
  { value: 8, label: 'High' },
  { value: 10, label: 'Best' },
];

function ProfileModal({
  initial,
  existing,
  onClose,
}: {
  initial: { id?: number; name: string; settings: ProfileSettings };
  existing?: Profile;
  onClose: () => void;
}) {
  const save = useSaveProfile();
  const remove = useDeleteProfile();
  const form = useForm({
    initialValues: initial,
    validate: { name: (v) => (v.trim() ? null : 'Give it a name') },
  });
  const s = form.values.settings;

  return (
    <Modal opened onClose={onClose} title={initial.id ? 'Edit profile' : 'New profile'} size="lg">
      <form
        onSubmit={form.onSubmit((values) =>
          save.mutate(values, {
            onSuccess: () => {
              notifications.show({ message: `Profile "${values.name}" saved.` });
              onClose();
            },
          }),
        )}
      >
        <Stack>
          <TextInput label="Name" {...form.getInputProps('name')} />
          <div>
            <Text size="sm" fw={500} mb={4}>
              Video codec
            </Text>
            <SegmentedControl
              data={Object.entries(CODEC_LABELS).map(([value, label]) => ({ value, label }))}
              {...form.getInputProps('settings.codec')}
            />
            <Text size="xs" c="dimmed" mt={4}>
              HEVC plays almost everywhere. AV1 is smaller but needs newer GPUs and players.
            </Text>
          </div>
          <div>
            <Text size="sm" fw={500} mb={4}>
              Quality
            </Text>
            <Slider
              min={1}
              max={10}
              step={1}
              marks={QUALITY_MARKS}
              mb="lg"
              {...form.getInputProps('settings.quality')}
            />
          </div>
          <div>
            <Text size="sm" fw={500} mb={4}>
              Speed
            </Text>
            <SegmentedControl
              data={[
                { value: 'fast', label: 'Fast' },
                { value: 'balanced', label: 'Balanced' },
                { value: 'slow', label: 'Slow (smaller files)' },
              ]}
              {...form.getInputProps('settings.speed')}
            />
          </div>
          <Switch
            label="10-bit output"
            description="Better quality per byte and no colour banding. Not available for H.264."
            disabled={s.codec === 'h264'}
            {...form.getInputProps('settings.ten_bit', { type: 'checkbox' })}
          />
          <Select
            label="Maximum resolution"
            description="Larger videos are scaled down; smaller ones are never scaled up."
            data={[
              { value: '', label: 'Keep the source resolution' },
              { value: '2160', label: '2160p (4K)' },
              { value: '1440', label: '1440p' },
              { value: '1080', label: '1080p' },
              { value: '720', label: '720p' },
            ]}
            value={s.max_height ? String(s.max_height) : ''}
            onChange={(v) =>
              form.setFieldValue(
                'settings.max_height',
                v ? (Number(v) as ProfileSettings['max_height']) : null,
              )
            }
          />
          <Select
            label="Audio"
            data={[
              { value: 'copy', label: 'Copy every track unchanged' },
              {
                value: 'compress_lossless',
                label: 'Compress lossless tracks (TrueHD, DTS-HD MA, FLAC, PCM) to E-AC-3',
              },
            ]}
            {...form.getInputProps('settings.audio')}
          />
          <Switch
            label="Add a stereo AAC track for older devices"
            {...form.getInputProps('settings.add_stereo_aac', { type: 'checkbox' })}
          />
          <Text size="xs" c="dimmed">
            Atmos and DTS:X audio is always copied unchanged. Dolby Vision files are skipped.
          </Text>
          {(save.isError || remove.isError) && (
            <Alert color="red">{errorMessage(save.error ?? remove.error)}</Alert>
          )}
          <Group justify="space-between">
            {existing && !existing.builtin ? (
              <Button
                variant="subtle"
                color="red"
                loading={remove.isPending}
                onClick={() => remove.mutate(existing.id, { onSuccess: onClose })}
              >
                Delete
              </Button>
            ) : (
              <span />
            )}
            <Group gap="xs">
              <Button variant="default" onClick={onClose}>
                Cancel
              </Button>
              <Button type="submit" loading={save.isPending}>
                Save
              </Button>
            </Group>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
