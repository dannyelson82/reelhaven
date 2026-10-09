import {
  Alert,
  Button,
  Group,
  Loader,
  Modal,
  MultiSelect,
  Select,
  Stack,
  Switch,
  Text,
} from '@mantine/core';
import { useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import { errorMessage } from '../api/client';
import { type LanguagePolicy, usePolicy, useSavePolicy } from '../api/policy';
import { useLanguages } from '../api/titles';

export function PolicyModal({ libraryId, onClose }: { libraryId: number; onClose: () => void }) {
  const policy = usePolicy(libraryId);
  return (
    <Modal opened onClose={onClose} title="Language policy" size="lg">
      {policy.isPending && <Loader />}
      {policy.isError && <Alert color="red">{errorMessage(policy.error)}</Alert>}
      {policy.data && <PolicyForm libraryId={libraryId} initial={policy.data} onClose={onClose} />}
    </Modal>
  );
}

function PolicyForm({
  libraryId,
  initial,
  onClose,
}: {
  libraryId: number;
  initial: LanguagePolicy;
  onClose: () => void;
}) {
  const languages = useLanguages();
  const save = useSavePolicy(libraryId);
  const form = useForm<LanguagePolicy>({
    initialValues: initial,
    validate: { keep_languages: (v) => (v.length ? null : 'Choose at least one language') },
  });
  const options = (languages.data ?? []).map((l) => ({ value: l.code, label: l.name }));

  return (
    <form
      onSubmit={form.onSubmit((values) =>
        save.mutate(values, {
          onSuccess: () => {
            notifications.show({ message: 'Language policy saved.' });
            onClose();
          },
        }),
      )}
    >
      <Stack>
        <Text size="sm" c="dimmed">
          Decides which audio and subtitle tracks to keep in this library. Nothing changes until you
          apply a dry run.
        </Text>
        <MultiSelect
          label="Languages you want"
          description="The first one is your own language: it decides which subtitles play by default."
          searchable
          data={options}
          {...form.getInputProps('keep_languages')}
        />
        <Switch
          label="Also keep each title's original language"
          description="E.g. Japanese audio for a Japanese film."
          {...form.getInputProps('keep_original', { type: 'checkbox' })}
        />
        <Text size="sm" fw={500}>
          Subtitles to keep (in wanted languages)
        </Text>
        <Group>
          <Switch
            label="Full"
            {...form.getInputProps('keep_subtitles_full', { type: 'checkbox' })}
          />
          <Switch
            label="Forced"
            {...form.getInputProps('keep_subtitles_forced', { type: 'checkbox' })}
          />
          <Switch
            label="SDH / hearing impaired"
            {...form.getInputProps('keep_subtitles_sdh', { type: 'checkbox' })}
          />
        </Group>
        <Switch
          label="Keep commentary tracks"
          {...form.getInputProps('keep_commentary', { type: 'checkbox' })}
        />
        <Select
          label="Tracks without a language tag"
          data={[{ value: 'keep', label: 'Always keep them (safest)' }, ...options]}
          searchable
          {...form.getInputProps('untagged')}
        />
        <Switch
          label="Set the default audio and subtitle tracks"
          description="Original-language audio; forced subtitles for your language, or full subtitles for foreign audio."
          {...form.getInputProps('set_defaults', { type: 'checkbox' })}
        />
        <Switch
          label="Show my language's subtitles automatically"
          description="Marks the default subtitle in your language as forced, so Plex and other players show it without you switching it on: forced subtitles for foreign lines, or full subtitles when the film is in another language."
          disabled={!form.values.set_defaults}
          {...form.getInputProps('force_subtitles', { type: 'checkbox' })}
        />
        {save.isError && <Alert color="red">{errorMessage(save.error)}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={save.isPending}>
            Save
          </Button>
        </Group>
      </Stack>
    </form>
  );
}
