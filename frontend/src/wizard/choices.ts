// Pure helpers for the wizard's choices (ADR-0026).
import type { Profile, ProfileSettings } from '../api/profiles';

export type AudioChoice = 'profile' | 'keep' | 'shrink' | 'stereo';

export const PRESETS = [
  {
    key: 'smallest',
    builtin: 'Small',
    title: 'Smallest',
    description: 'The most space saved. Fine on phones, tablets and most TVs.',
  },
  {
    key: 'balanced',
    builtin: 'Balanced',
    title: 'Balanced',
    description: 'Looks like the original on a TV, and still saves a lot. Recommended.',
  },
  {
    key: 'best',
    builtin: 'High quality',
    title: 'Best quality',
    description: 'For films you care about most. Saves less, takes longer.',
  },
] as const;

export const AUDIO_CHOICES: { key: AudioChoice; title: string; description: string }[] = [
  {
    key: 'keep',
    title: 'Keep audio as it is',
    description: 'Every soundtrack stays exactly as it is.',
  },
  {
    key: 'shrink',
    title: 'Shrink big audio tracks, keep surround',
    description:
      'Large lossless tracks become E-AC-3, which plays almost everywhere. Surround stays.',
  },
  {
    key: 'stereo',
    title: 'Stereo only (smallest)',
    description:
      'Every 5.1 and 7.1 track becomes stereo. Only if every screen and speaker is stereo.',
  },
];

/** Whether a profile already has its own audio setup (e.g. from Mimic a file). */
export function hasOwnAudio(settings: ProfileSettings): boolean {
  return settings.audio !== 'copy' || settings.downmix_stereo;
}

/** The audio answer to preselect: the profile's own setup when it has one. */
export function defaultAudioChoice(settings: ProfileSettings): AudioChoice {
  return hasOwnAudio(settings) ? 'profile' : 'keep';
}

/** The profile settings with one of the wizard's audio answers applied. A profile's own
 * codec and bitrate are kept wherever the answer allows. */
export function withAudio(settings: ProfileSettings, choice: AudioChoice): ProfileSettings {
  if (choice === 'profile') return settings;
  if (choice === 'keep') return { ...settings, audio: 'copy', downmix_stereo: false };
  const own = settings.audio !== 'copy';
  if (choice === 'shrink') {
    return {
      ...settings,
      audio: 'compress_lossless',
      audio_codec: own ? settings.audio_codec : 'eac3',
      audio_kbps_per_channel: own ? settings.audio_kbps_per_channel : null,
      downmix_stereo: false,
    };
  }
  return {
    ...settings,
    audio: 'convert',
    audio_codec: own ? settings.audio_codec : 'aac',
    audio_kbps_per_channel: own ? settings.audio_kbps_per_channel : null,
    downmix_stereo: true,
    add_stereo_aac: false,
  };
}

const canonical = (s: ProfileSettings) =>
  JSON.stringify(Object.fromEntries(Object.entries(s).sort(([a], [b]) => a.localeCompare(b))));

/** An existing profile with exactly these settings, built-in ones first. */
export function findProfile(profiles: Profile[], settings: ProfileSettings): Profile | undefined {
  const wanted = canonical(settings);
  return [...profiles]
    .sort((a, b) => Number(b.builtin) - Number(a.builtin))
    .find((p) => canonical(p.settings) === wanted);
}

/** "Balanced, smaller audio", made unique among existing names. */
export function profileName(base: string, choice: AudioChoice, taken: string[]): string {
  const suffix =
    choice === 'shrink' ? ', smaller audio' : choice === 'stereo' ? ', stereo audio' : '';
  const name = `${base}${suffix}`.slice(0, 90);
  if (!taken.includes(name)) return name;
  for (let n = 2; ; n++) {
    if (!taken.includes(`${name} (${n})`)) return `${name} (${n})`;
  }
}

/** Whether any enabled device passed the test encode for this format. */
export function canEncode(
  devices: { enabled: boolean; results: { codec: string; ten_bit: boolean; ok: boolean }[] }[],
  codec: string,
  tenBit: boolean,
): boolean {
  return devices.some(
    (d) => d.enabled && d.results.some((r) => r.ok && r.codec === codec && r.ten_bit === tenBit),
  );
}
