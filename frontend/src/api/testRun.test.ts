import { type TestSample, isUpNext } from './testRun';

const sample = (id: number, job_status: string | null): TestSample =>
  ({ id, job_status }) as TestSample;

it('a queued sample is up next while another one encodes', () => {
  const first = sample(1, 'running');
  const second = sample(2, 'queued');
  expect(isUpNext(second, [first, second])).toBe(true);
  expect(isUpNext(first, [first, second])).toBe(false);
  // Nothing encoding yet: it's waiting for an encoder, not for its turn.
  expect(isUpNext(second, [sample(1, 'queued'), second])).toBe(false);
  expect(isUpNext(second, [sample(1, 'done'), second])).toBe(false);
  expect(isUpNext(second, [sample(1, 'verifying'), second])).toBe(true);
});
