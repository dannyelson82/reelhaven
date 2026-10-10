import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from '../App';
import { mockApi, state } from '../test/mockApi';

const loggedIn = state({ authenticated: true, username: 'admin', method: 'session' });
const counts = { wrong_language: 1, failed: 1, unreadable: 0, skipped: 0, no_gain: 0, waiting: 3 };
const item = (kind: string, extra: object) => ({
  kind,
  file_id: 11,
  library_id: 4,
  library_name: 'TV Shows',
  relative_path: 'Show/S01E01.mkv',
  size: 2e9,
  detail: '',
  ignored: false,
  job_id: null,
  original_language: null,
  audio_languages: [],
  ...extra,
});

afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = '';
});

it('lists files to review and acts on them', async () => {
  window.location.hash = '#/review';
  const calls = mockApi({
    'GET auth/state': loggedIn,
    'GET review?offset=0&limit=1': { body: { counts, ignored: 0, total: 5, items: [] } },
    'GET review?kind=wrong_language&offset=0&limit=100': {
      body: {
        counts,
        ignored: 0,
        total: 1,
        items: [
          item('wrong_language', { original_language: 'eng', audio_languages: ['spa', 'fre'] }),
        ],
      },
    },
    'GET review?kind=failed&offset=0&limit=100': {
      body: {
        counts,
        ignored: 0,
        total: 1,
        items: [item('failed', { detail: 'decode test failed at 12s', job_id: 9 })],
      },
    },
    'PUT review/ignore': { status: 204 },
    'POST jobs/9/retry': { body: {} },
  });
  render(<App />);
  expect(
    await screen.findByText(/Audio: Spanish, French · original language: English/),
  ).toBeInTheDocument();
  expect(await screen.findByLabelText('2 files to review')).toBeInTheDocument(); // waiting left out
  await userEvent.click(screen.getByRole('button', { name: 'Ignore' }));
  const ignored = calls.find((c) => c.key === 'PUT review/ignore');
  expect(JSON.parse(String(ignored?.init?.body))).toEqual({
    file_id: 11,
    kind: 'wrong_language',
    ignored: true,
  });

  await userEvent.click(screen.getByRole('tab', { name: /Failed/ }));
  expect(await screen.findByText('decode test failed at 12s')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
  expect(calls.some((c) => c.key === 'POST jobs/9/retry')).toBe(true);
  expect(screen.getByRole('link', { name: 'Open library' })).toHaveAttribute(
    'href',
    '#/libraries/4',
  );
});
