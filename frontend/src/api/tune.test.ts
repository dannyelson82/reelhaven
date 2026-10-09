import { nextQualities } from './tune';

it('suggests what to try next', () => {
  expect(nextQualities([8, 6, 4])).toEqual({
    better: 9,
    smaller: 3,
    between: [
      [8, 6, 7],
      [6, 4, 5],
    ],
  });
  // Half steps fill the last gaps; gaps under a whole level are done.
  expect(nextQualities([7, 6, 6.5]).between).toEqual([]);
  expect(nextQualities([7, 6]).between).toEqual([[7, 6, 6.5]]);
  expect(nextQualities([6, 4.5]).between).toEqual([[6, 4.5, 5.5]]);
  expect(nextQualities([10, 1])).toMatchObject({ better: null, smaller: null });
  expect(nextQualities([])).toEqual({ better: null, smaller: null, between: [] });
});
