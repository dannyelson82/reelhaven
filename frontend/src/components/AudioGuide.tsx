import { Anchor, Badge, Collapse, Group, Stack, Table, Text } from '@mantine/core';
import { useState } from 'react';
import { AUDIO_LEVELS, PLAYS_EVERYWHERE, levelFor } from '../api/audioGuide';
import {
  AUDIO_CODEC_LABELS,
  DEFAULT_KBPS_PER_CHANNEL,
  type ProfileSettings,
  trackKbps,
} from '../api/profiles';

const GRADE_COLOR = ['orange', 'yellow', 'teal', 'gray'] as const;

/** What the chosen audio bitrate means, with a chart per format and the Plex note. */
export function AudioGuide({ settings }: { settings: ProfileSettings }) {
  const [chart, setChart] = useState(false);
  const codec = settings.audio_codec;
  const per = settings.audio_kbps_per_channel ?? DEFAULT_KBPS_PER_CHANNEL[codec];
  const level = levelFor(codec, per);
  const at = (perChannel: number, channels: number) =>
    trackKbps({ ...settings, audio_kbps_per_channel: perChannel }, channels);
  const label = AUDIO_CODEC_LABELS[codec];
  return (
    <Stack gap={6}>
      <Group gap="xs">
        <Text size="sm">
          {label} at {per} kbit/s per channel (stereo {at(per, 2)}
          {!settings.downmix_stereo && `, 5.1 ${at(per, 6)}`} kbit/s):
        </Text>
        <Badge color={GRADE_COLOR[level.grade]} variant="light">
          {level.verdict}
        </Badge>
      </Group>
      <Text size="xs" c="dimmed">
        Plex converts audio that a TV or player can't play itself while you watch, which costs your
        server CPU. E-AC-3 is the safest choice for playing everywhere without that. {label}:{' '}
        {PLAYS_EVERYWHERE[codec]}{' '}
        <Anchor size="xs" component="button" type="button" onClick={() => setChart((c) => !c)}>
          {chart ? 'Hide the chart' : 'What do the bitrates mean?'}
        </Anchor>
      </Text>
      <Collapse expanded={chart}>
        <Table striped withTableBorder fz="sm">
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{label}, per channel</Table.Th>
              <Table.Th>Stereo</Table.Th>
              <Table.Th>5.1</Table.Th>
              <Table.Th>What you&apos;ll hear</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {AUDIO_LEVELS[codec].map((l) => (
              <Table.Tr
                key={l.perChannel}
                fw={l === level ? 700 : undefined}
                aria-current={l === level ? 'true' : undefined}
              >
                <Table.Td>{l.perChannel} kbit/s</Table.Td>
                <Table.Td>{at(l.perChannel, 2)}</Table.Td>
                <Table.Td>{at(l.perChannel, 6)}</Table.Td>
                <Table.Td>{l.verdict}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
        <Text size="xs" c="dimmed" mt={4}>
          For comparison, a film&apos;s original lossless 5.1 track (TrueHD, DTS-HD MA) is usually
          2,000 to 4,500 kbit/s. Tracks are never made bigger: a track already below the target is
          copied.
        </Text>
      </Collapse>
    </Stack>
  );
}
