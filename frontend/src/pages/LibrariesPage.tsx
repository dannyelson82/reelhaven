import {
  Alert,
  Anchor,
  Badge,
  Button,
  Card,
  Code,
  Group,
  Loader,
  Modal,
  SegmentedControl,
  Select,
  Stack,
  Switch,
  Text,
  TextInput,
  Title,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import { IconPlus } from '@tabler/icons-react';
import { useState } from 'react';
import { Link } from 'react-router';
import { useAutomation, useSaveAutomation } from '../api/automation';
import { errorMessage } from '../api/client';
import {
  LIBRARY_TYPES,
  type Library,
  type LibraryType,
  useCreateLibrary,
  useDeleteLibrary,
  useLibraries,
  useUpdateLibrary,
} from '../api/libraries';
import { FolderPicker } from '../components/FolderPicker';

const typeLabel = (type: LibraryType) => LIBRARY_TYPES.find((t) => t.value === type)?.label;

export function LibrariesPage() {
  const libraries = useLibraries();
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<Library | null>(null);

  return (
    <Stack maw={900}>
      <Group justify="space-between">
        <Title order={2}>Libraries</Title>
        <Group gap="xs">
          <Anchor component="button" size="sm" c="dimmed" onClick={() => setAdding(true)}>
            Add without the wizard
          </Anchor>
          <Button leftSection={<IconPlus size={16} />} component={Link} to="/wizard">
            Add library
          </Button>
        </Group>
      </Group>
      {libraries.isPending && <Loader />}
      {libraries.isError && <Alert color="red">{errorMessage(libraries.error)}</Alert>}
      {libraries.data?.length === 0 && (
        <Card withBorder>
          <Text c="dimmed">
            No libraries yet. Add one for each kind of media, for example your Movies folder and
            your TV folder.
          </Text>
        </Card>
      )}
      {libraries.data?.map((library) => (
        <Card key={library.id} withBorder>
          <Group justify="space-between">
            <Stack gap={2}>
              <Group gap="xs">
                <Text fw={600} component={Link} to={`/libraries/${library.id}`} c="inherit">
                  {library.name}
                </Text>
                <Badge variant="light">{typeLabel(library.type)}</Badge>
                {library.watch_mode !== 'off' && (
                  <Badge
                    variant="light"
                    color={library.watch_mode === 'automatic' ? 'teal' : 'blue'}
                  >
                    {library.watch_mode === 'automatic' ? 'Automatic' : 'Watching'}
                  </Badge>
                )}
              </Group>
              <Code>{library.path}</Code>
              <Text size="xs" c="dimmed">
                {library.file_count} files
                {library.last_scan_at
                  ? ` · last scanned ${new Date(library.last_scan_at).toLocaleString()}`
                  : ' · not scanned yet'}
              </Text>
            </Stack>
            <Group gap="xs">
              <Button component={Link} to={`/libraries/${library.id}`} variant="light">
                Open
              </Button>
              <Button variant="default" onClick={() => setEditing(library)}>
                Edit
              </Button>
            </Group>
          </Group>
        </Card>
      ))}
      {libraries.data && libraries.data.length > 0 && <RescanCard />}
      <AddLibraryModal opened={adding} onClose={() => setAdding(false)} />
      {editing && <EditLibraryModal library={editing} onClose={() => setEditing(null)} />}
    </Stack>
  );
}

function AddLibraryModal({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const create = useCreateLibrary();
  const form = useForm({
    initialValues: { name: '', type: 'movies' as LibraryType, path: '' },
    validate: {
      name: (v) => (v.trim() ? null : 'Give the library a name'),
      path: (v) => (v ? null : 'Choose a folder'),
    },
  });
  const close = () => {
    form.reset();
    create.reset();
    onClose();
  };

  return (
    <Modal opened={opened} onClose={close} title="Add library" size="lg">
      <form
        onSubmit={form.onSubmit((values) =>
          create.mutate(values, {
            onSuccess: (library) => {
              notifications.show({ message: `Library "${library.name}" added.` });
              close();
            },
          }),
        )}
      >
        <Stack>
          <TextInput label="Name" placeholder="Movies" {...form.getInputProps('name')} />
          <div>
            <Text size="sm" fw={500} mb={4}>
              Type
            </Text>
            <SegmentedControl data={LIBRARY_TYPES} {...form.getInputProps('type')} />
          </div>
          <div>
            <Text size="sm" fw={500} mb={4}>
              Folder
            </Text>
            <FolderPicker
              value={form.values.path}
              onChange={(path) => form.setFieldValue('path', path)}
            />
            <Text size="sm" mt={4}>
              Selected: <Code>/media/{form.values.path}</Code>
            </Text>
            {form.errors.path && (
              <Text size="sm" c="red">
                {form.errors.path}
              </Text>
            )}
          </div>
          <Text size="sm" c="dimmed">
            Adding a library doesn't change any files.
          </Text>
          {create.isError && <Alert color="red">{errorMessage(create.error)}</Alert>}
          <Group justify="flex-end">
            <Button variant="default" onClick={close}>
              Cancel
            </Button>
            <Button type="submit" loading={create.isPending}>
              Add library
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}

function EditLibraryModal({ library, onClose }: { library: Library; onClose: () => void }) {
  const update = useUpdateLibrary();
  const remove = useDeleteLibrary();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const form = useForm({ initialValues: { name: library.name, type: library.type } });

  return (
    <Modal opened onClose={onClose} title={`Edit ${library.name}`}>
      <form
        onSubmit={form.onSubmit((values) =>
          update.mutate({ id: library.id, ...values }, { onSuccess: onClose }),
        )}
      >
        <Stack>
          <TextInput label="Name" {...form.getInputProps('name')} />
          <SegmentedControl data={LIBRARY_TYPES} {...form.getInputProps('type')} />
          <Text size="sm">
            Folder: <Code>{library.path}</Code>
          </Text>
          {(update.isError || remove.isError) && (
            <Alert color="red">{errorMessage(update.error ?? remove.error)}</Alert>
          )}
          {confirmDelete ? (
            <Alert color="red" title="Remove this library?">
              <Stack gap="xs">
                <Text size="sm">
                  ReelHaven forgets the library. Your files stay exactly where they are.
                </Text>
                <Group>
                  <Button
                    color="red"
                    loading={remove.isPending}
                    onClick={() => remove.mutate(library.id, { onSuccess: onClose })}
                  >
                    Remove library
                  </Button>
                  <Button variant="default" onClick={() => setConfirmDelete(false)}>
                    Keep it
                  </Button>
                </Group>
              </Stack>
            </Alert>
          ) : (
            <Group justify="space-between">
              <Button variant="subtle" color="red" onClick={() => setConfirmDelete(true)}>
                Remove library
              </Button>
              <Button type="submit" loading={update.isPending}>
                Save
              </Button>
            </Group>
          )}
        </Stack>
      </form>
    </Modal>
  );
}

const TIMES = Array.from({ length: 48 }, (_, i) => {
  const value = `${String(Math.floor(i / 2)).padStart(2, '0')}:${i % 2 ? '30' : '00'}`;
  return { value, label: value };
});

/** The nightly rescan of watched libraries (ADR-0025). */
function RescanCard() {
  const automation = useAutomation();
  const save = useSaveAutomation();
  const data = automation.data;
  if (!data) return null;
  return (
    <Card withBorder>
      <Group justify="space-between" align="flex-end">
        <Stack gap={2}>
          <Switch
            label="Rescan watched libraries every night"
            checked={data.rescan_enabled}
            disabled={save.isPending}
            onChange={(e) => save.mutate({ ...data, rescan_enabled: e.currentTarget.checked })}
          />
          <Text size="xs" c="dimmed">
            Libraries set to Watch or Automatic are scanned once a day, to catch anything missed.
          </Text>
        </Stack>
        {data.rescan_enabled && (
          <Select
            aria-label="Rescan time"
            w={110}
            allowDeselect={false}
            data={TIMES}
            value={data.rescan_at}
            disabled={save.isPending}
            onChange={(value) => value && save.mutate({ ...data, rescan_at: value })}
          />
        )}
      </Group>
      {save.isError && (
        <Text size="sm" c="red">
          {errorMessage(save.error)}
        </Text>
      )}
    </Card>
  );
}
