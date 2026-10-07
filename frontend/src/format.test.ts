import { formatTimeLeft } from './format';

it('formats time left roughly', () => {
  expect(formatTimeLeft(20)).toBe('under a minute');
  expect(formatTimeLeft(89)).toBe('1 min');
  expect(formatTimeLeft(12 * 60)).toBe('12 min');
  expect(formatTimeLeft(3600 + 5 * 60)).toBe('1 h 05 min');
  expect(formatTimeLeft(59.6 * 60)).toBe('1 h 00 min');
});
