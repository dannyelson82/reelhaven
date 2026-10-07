import type { Profile, ProfileSettings } from '../api/profiles';
import { canEncode, findProfile, profileName, withAudio } from './choices';

const balanced: ProfileSettings = {
  codec: 'hevc',
  quality: 6,
  speed: 'balanced',
  ten_bit: true,
  max_height: null,
  audio: 'copy',
  audio_codec: 'eac3',
  audio_kbps_per_channel: null,
  downmix_stereo: false,
  add_stereo_aac: false,
  min_savings_percent: 10,
};
const profile = (
  id: number,
  name: string,
  settings: ProfileSettings,
  builtin = false,
): Profile => ({
  id,
  name,
  builtin,
  settings,
  source: 'manual',
  mimic: null,
  used_by: [],
  updated_at: '',
});

it('applies the audio answers', () => {
  expect(withAudio(balanced, 'keep')).toEqual(balanced);
  expect(withAudio(balanced, 'shrink')).toMatchObject({
    audio: 'compress_lossless',
    audio_codec: 'eac3',
  });
  expect(withAudio({ ...balanced, add_stereo_aac: true }, 'stereo')).toMatchObject({
    audio: 'convert',
    audio_codec: 'aac',
    downmix_stereo: true,
    add_stereo_aac: false,
  });
});

it('reuses a profile with the same settings, built-in first', () => {
  const custom = profile(5, 'Mine', { ...balanced });
  const builtin = profile(2, 'Balanced', { ...balanced }, true);
  expect(findProfile([custom, builtin], balanced)?.id).toBe(2);
  // Key order doesn't matter.
  const reordered = Object.fromEntries(Object.entries(balanced).reverse()) as ProfileSettings;
  expect(findProfile([custom], reordered)?.id).toBe(5);
  expect(findProfile([builtin], withAudio(balanced, 'shrink'))).toBeUndefined();
});

it('names new profiles readably and uniquely', () => {
  expect(profileName('Balanced', 'shrink', [])).toBe('Balanced, smaller audio');
  expect(profileName('Balanced', 'stereo', ['Balanced, stereo audio'])).toBe(
    'Balanced, stereo audio (2)',
  );
  expect(profileName('Small', 'keep', ['Small'])).toBe('Small (2)');
});

it('knows whether anything can encode', () => {
  const gpu = { enabled: true, results: [{ codec: 'hevc', ten_bit: true, ok: true }] };
  const off = { ...gpu, enabled: false };
  const cpu = { enabled: false, results: [{ codec: 'av1', ten_bit: true, ok: true }] };
  expect(canEncode([gpu], 'hevc', true)).toBe(true);
  expect(canEncode([off, cpu], 'hevc', true)).toBe(false);
  expect(canEncode([gpu], 'hevc', false)).toBe(false);
  expect(canEncode([gpu, { ...cpu, enabled: true }], 'av1', true)).toBe(true);
});
