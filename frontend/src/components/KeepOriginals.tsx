// Choosing how long replaced originals are kept (ADR-0028). Used on the Recycle bin page and
// in the setup wizard.
import { Alert, SegmentedControl, Stack, Text } from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import {
  KEEP_DAYS,
  type KeepDays,
  originalsSentence,
  useRecycleSettings,
} from '../api/recycleSettings';

const label = (days: KeepDays) => (days === 0 ? 'Off' : `${days} ${days === 1 ? 'day' : 'days'}`);

export function KeepOriginalsControl({
  value,
  onChange,
}: {
  value: KeepDays;
  onChange: (days: KeepDays) => void;
}) {
  // Six options don't fit side by side on a phone: stack them there.
  const narrow = useMediaQuery('(max-width: 36em)');
  return (
    <Stack gap="xs">
      <SegmentedControl
        aria-label="Keep originals for"
        data={KEEP_DAYS.map((days) => ({ value: String(days), label: label(days) }))}
        value={String(value)}
        onChange={(v) => onChange(Number(v) as KeepDays)}
        orientation={narrow ? 'vertical' : 'horizontal'}
        fullWidth
      />
      {value === 0 ? (
        <Alert color="orange" title="No undo">
          Originals are deleted as soon as the new file has passed its checks. You get the space
          back straight away, but a file can't be put back if you don't like the result, and
          surround sound removed by a stereo downmix is gone for good.
        </Alert>
      ) : (
        <Text size="sm" c="dimmed">
          14 days is recommended. The space comes back when an original leaves the bin: shorter is
          quicker, longer gives you more time to notice a problem.
        </Text>
      )}
    </Stack>
  );
}

/** The sentence about what happens to originals, following the setting. */
export function OriginalsNote() {
  return <>{originalsSentence(useRecycleSettings().data?.keep_days)}</>;
}
