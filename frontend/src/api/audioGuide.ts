// What audio bitrates mean, per format (ADR-0031). General guidance for films and series
// played on a TV or home cinema, not measurements of a particular file.
import type { AudioCodec } from './profiles';

export interface Level {
  /** Bitrate per channel (kbit/s) where this level starts. */
  perChannel: number;
  verdict: string;
  /** How good it is, for colouring: 0 = noticeably reduced … 3 = more than needed. */
  grade: 0 | 1 | 2 | 3;
}

export const AUDIO_LEVELS: Record<AudioCodec, Level[]> = {
  eac3: [
    { perChannel: 32, verdict: 'Reduced: fine on TV speakers, thin on a good system', grade: 0 },
    { perChannel: 64, verdict: 'Streaming quality, like most streaming services', grade: 1 },
    { perChannel: 96, verdict: 'Very good: hard to tell from the original', grade: 2 },
    { perChannel: 112, verdict: 'Transparent for most listeners', grade: 2 },
    { perChannel: 160, verdict: 'No audible gain, just bigger', grade: 3 },
  ],
  aac: [
    { perChannel: 32, verdict: 'Reduced: speech is fine, music and effects sound dull', grade: 0 },
    { perChannel: 48, verdict: 'Good on TV speakers', grade: 1 },
    { perChannel: 64, verdict: 'Very good: hard to tell from the original', grade: 2 },
    { perChannel: 96, verdict: 'Transparent for most listeners', grade: 2 },
    { perChannel: 128, verdict: 'No audible gain, just bigger', grade: 3 },
  ],
  opus: [
    { perChannel: 16, verdict: 'Reduced: speech is fine, music and effects sound dull', grade: 0 },
    { perChannel: 32, verdict: 'Good: hard to tell on most systems', grade: 1 },
    { perChannel: 48, verdict: 'Transparent for most listeners', grade: 2 },
    { perChannel: 80, verdict: 'No audible gain, just bigger', grade: 3 },
  ],
};

/** The level a bitrate per channel falls in (the lowest level below its first step). */
export function levelFor(codec: AudioCodec, perChannel: number): Level {
  const levels = AUDIO_LEVELS[codec];
  return [...levels].reverse().find((l) => perChannel >= l.perChannel) ?? levels[0];
}

/** Whether a format plays on (nearly) every TV, stick and soundbar without Plex converting
 * it while you watch. */
export const PLAYS_EVERYWHERE: Record<AudioCodec, string> = {
  eac3: 'Plays directly on almost every TV, streaming stick and soundbar.',
  aac: 'Plays everywhere in stereo; some players and soundbars convert 5.1 AAC to stereo.',
  opus: "Many TVs, sticks and soundbars can't play it, so Plex converts it while you watch.",
};
