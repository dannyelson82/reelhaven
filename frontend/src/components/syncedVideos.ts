// Two videos that play, pause and seek together (ADR-0031): the original leads, the new
// file follows it.
import { type RefObject, useEffect, useRef, useState } from 'react';

/** How the follower catches up with the leader, `diff` seconds ahead (+) or behind (−):
 * a jump when far off, otherwise a slightly faster or slower speed, which doesn't stutter. */
export function correction(diff: number): { jump: boolean; rate: number } {
  if (Math.abs(diff) > 0.4) return { jump: true, rate: 1 };
  if (Math.abs(diff) > 0.03) return { jump: false, rate: diff > 0 ? 0.9 : 1.1 };
  return { jump: false, rate: 1 };
}

// The elements are changed outside the hook: they belong to the page, not to React.
function moveTo(videos: (HTMLVideoElement | null)[], seconds: number) {
  for (const video of videos) if (video) video.currentTime = seconds;
}

function follow(video: HTMLVideoElement, leader: HTMLVideoElement, rate = 1) {
  video.currentTime = leader.currentTime;
  video.playbackRate = rate;
}

export interface SyncedVideos {
  playing: boolean;
  time: number;
  duration: number;
  play: () => void;
  pause: () => void;
  toggle: () => void;
  seek: (seconds: number) => void;
}

export function useSyncedVideos(
  leader: RefObject<HTMLVideoElement | null>,
  follower: RefObject<HTMLVideoElement | null>,
  /** Changes whenever the two elements are replaced (e.g. a new layout). */
  key: unknown,
): SyncedVideos {
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const wanted = useRef(false);
  const last = useRef(0);

  const pause = () => {
    wanted.current = false;
    const a = leader.current;
    const b = follower.current;
    a?.pause();
    b?.pause();
    if (a && b) follow(b, a);
    setPlaying(false);
  };

  const play = () => {
    const a = leader.current;
    const b = follower.current;
    if (!a || !b) return;
    wanted.current = true;
    follow(b, a);
    Promise.all([a.play(), b.play()]).then(
      () => setPlaying(wanted.current),
      () => pause(),
    );
  };

  const seek = (seconds: number) => {
    moveTo([leader.current, follower.current], seconds);
    last.current = seconds;
    setTime(seconds);
  };

  // While playing, keep the follower on the leader's frame; loop at the end.
  useEffect(() => {
    const a = leader.current;
    const b = follower.current;
    if (!a || !b) return;
    let frame = 0;
    const tick = () => {
      last.current = a.currentTime;
      setTime(a.currentTime);
      if (wanted.current && !a.paused) {
        const { jump, rate } = correction(b.currentTime - a.currentTime);
        if (jump) follow(b, a);
        else b.playbackRate = rate;
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    const onMeta = () => {
      setDuration(Number.isFinite(a.duration) ? a.duration : 0);
      // A new pair (another layout) carries on, paused, where the old pair was.
      moveTo([a, b], last.current);
    };
    const onEnded = () => {
      if (!wanted.current) return;
      moveTo([a, b], 0);
      void Promise.all([a.play(), b.play()]).catch(() => {
        wanted.current = false;
        setPlaying(false);
      });
    };
    onMeta();
    a.addEventListener('loadedmetadata', onMeta);
    a.addEventListener('ended', onEnded);
    return () => {
      wanted.current = false;
      setPlaying(false);
      cancelAnimationFrame(frame);
      a.removeEventListener('loadedmetadata', onMeta);
      a.removeEventListener('ended', onEnded);
    };
  }, [leader, follower, key]);

  const toggle = () => (playing ? pause() : play());
  return { playing, time, duration, play, pause, toggle, seek };
}
