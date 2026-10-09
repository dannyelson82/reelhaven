import { AUDIO_LEVELS, levelFor } from './audioGuide';
import { DEFAULT_KBPS_PER_CHANNEL } from './profiles';

it('finds the level a bitrate falls in', () => {
  expect(levelFor('eac3', 112).verdict).toBe('Transparent for most listeners');
  expect(levelFor('eac3', 100).verdict).toMatch(/^Very good/);
  expect(levelFor('eac3', 16).grade).toBe(0); // below the first step: the lowest level
  expect(levelFor('opus', 256).grade).toBe(3);
});

it('calls every default bitrate good without being wasteful', () => {
  for (const [codec, per] of Object.entries(DEFAULT_KBPS_PER_CHANNEL)) {
    expect(levelFor(codec as keyof typeof AUDIO_LEVELS, per).grade).toBe(2);
  }
});

it('lists the levels from low to high', () => {
  for (const levels of Object.values(AUDIO_LEVELS)) {
    const steps = levels.map((l) => l.perChannel);
    expect(steps).toEqual([...steps].sort((a, b) => a - b));
  }
});
