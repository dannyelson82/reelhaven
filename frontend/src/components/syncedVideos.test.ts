import { correction } from './syncedVideos';

it('nudges a follower that drifts and jumps when far off', () => {
  expect(correction(0.01)).toEqual({ jump: false, rate: 1 }); // in step
  expect(correction(0.1)).toEqual({ jump: false, rate: 0.9 }); // ahead: slow down
  expect(correction(-0.1)).toEqual({ jump: false, rate: 1.1 }); // behind: speed up
  expect(correction(2).jump).toBe(true);
  expect(correction(-2).jump).toBe(true);
});
