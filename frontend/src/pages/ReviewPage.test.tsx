import { render, screen, within } from '@testing-library/react';
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
    'POST files/11/wrong-language': { status: 201, body: { job_id: 12 } },
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

  // Quarantine asks first, then queues the job.
  await userEvent.click(screen.getByRole('button', { name: 'Quarantine' }));
  const dialog = await screen.findByRole('dialog', { name: 'Quarantine this file?' });
  await userEvent.click(within(dialog).getByRole('button', { name: 'Quarantine' }));
  const moved = calls.find((c) => c.key === 'POST files/11/wrong-language');
  expect(JSON.parse(String(moved?.init?.body))).toEqual({ action: 'quarantine' });

  await userEvent.click(screen.getByRole('tab', { name: /Failed/ }));
  expect(await screen.findByText('decode test failed at 12s')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
  expect(calls.some((c) => c.key === 'POST jobs/9/retry')).toBe(true);
  expect(screen.getByRole('link', { name: 'Open library' })).toHaveAttribute(
    'href',
    '#/libraries/4',
  );
});

it('keeps results off the Review page and lists them under Stats', async () => {
  const kept = {
    wrong_language: 1,
    failed: 0,
    unreadable: 0,
    skipped: 136,
    no_gain: 195,
    waiting: 0,
  };
  const page = (items: object[]) => ({
    body: { counts: kept, ignored: 0, total: items.length, items },
  });
  window.location.hash = '#/review';
  mockApi({
    'GET auth/state': loggedIn,
    'GET review?offset=0&limit=1': page([]),
    'GET review?kind=wrong_language&offset=0&limit=100': page([]),
    'GET review?kind=no_gain&offset=0&limit=50': page([
      item('no_gain', { detail: "Re-encoding with this profile didn't save enough." }),
    ]),
    'GET stats/performance': { body: { devices: [], daily: [] } },
    'GET stats/savings': {
      body: {
        total_saved: 0,
        files: 0,
        this_week: 0,
        this_month: 0,
        weekly: [],
        monthly: [],
        libraries: [],
      },
    },
  });
  render(<App />);
  expect(await screen.findByRole('tab', { name: /Wrong language/ })).toBeInTheDocument();
  expect(screen.queryByRole('tab', { name: /No gain/ })).not.toBeInTheDocument();
  expect(screen.queryByRole('tab', { name: /Not re-encoded/ })).not.toBeInTheDocument();
  // The menu counts only what needs a decision: 1, not 332.
  expect(await screen.findByLabelText('1 files to review')).toBeInTheDocument();

  window.location.hash = '#/stats';
  expect(await screen.findByText('Kept as is')).toBeInTheDocument();
  expect(await screen.findByText(/No gain \(195\)/)).toBeInTheDocument();
  expect(
    await screen.findByText("Re-encoding with this profile didn't save enough."),
  ).toBeInTheDocument();
});

it('lists wrong-colour files with Quarantine and Delete', async () => {
  const c = {
    wrong_language: 0,
    wrong_colours: 1,
    failed: 0,
    unreadable: 0,
    skipped: 0,
    no_gain: 0,
    waiting: 0,
  };
  const detail = 'Green and purple picture: probably a Dolby Vision profile 5 file.';
  window.location.hash = '#/review?kind=wrong_colours';
  mockApi({
    'GET auth/state': loggedIn,
    'GET review?offset=0&limit=1': { body: { counts: c, ignored: 0, total: 1, items: [] } },
    'GET review?kind=wrong_colours&offset=0&limit=100': {
      body: { counts: c, ignored: 0, total: 1, items: [item('wrong_colours', { detail })] },
    },
  });
  render(<App />);
  expect(await screen.findByRole('tab', { name: /Wrong colours/ })).toBeInTheDocument();
  expect(await screen.findByText(detail)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Quarantine' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument();
});
