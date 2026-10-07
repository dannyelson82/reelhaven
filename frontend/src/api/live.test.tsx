import { act, render, screen } from '@testing-library/react';
import { App } from '../App';
import { FakeSocket, push } from '../test/fakeSocket';
import { mockApi, state } from '../test/mockApi';

const running = {
  id: 7,
  library_id: 1,
  library_name: 'Movies',
  media_file_id: 9,
  file: 'Film (2020)/film.mkv',
  type: 'encode',
  status: 'running',
  progress: 0.1,
  summary: 'Re-encode to HEVC.',
  details: [],
  error: null,
  requested_by: 'admin',
  created_at: '2026-10-07T10:00:00Z',
  started_at: '2026-10-07T10:00:00Z',
  finished_at: null,
  bytes_before: null,
  bytes_after: null,
  process_seconds: null,
  outcome: null,
  device: 'cpu',
  fps: 30,
  speed: 1.2,
  eta_seconds: null,
};
const jobsPage = (items: unknown[], counts: Record<string, number>) => ({
  body: { total: items.length, counts, items },
});

afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = '';
});

it('updates job progress from the socket', async () => {
  window.location.hash = '#/jobs';
  const calls = mockApi({
    'GET auth/state': state({ authenticated: true, username: 'admin', method: 'session' }),
    'GET jobs?status=all&offset=0&limit=50': jobsPage([running], { running: 1 }),
  });
  render(<App />);
  expect(await screen.findByText(/10% · cpu · 30 fps/)).toBeInTheDocument();
  expect(FakeSocket.instances[0]?.url).toMatch(/^ws:\/\/.*\/api\/v1\/ws$/);

  act(() =>
    push({
      type: 'jobs',
      counts: { running: 1, queued: 2 },
      active: [{ ...running, progress: 0.6, fps: 52, eta_seconds: 300 }],
    }),
  );
  expect(
    await screen.findByText(/60% · cpu · 52 fps · 1\.2× real time · 5 min left/),
  ).toBeInTheDocument();
  expect(screen.getByLabelText('3 jobs in progress')).toBeInTheDocument();
  expect(screen.getByText('In progress (3)')).toBeInTheDocument();

  // Progress alone doesn't refetch the list; a job finishing does.
  const listed = () => calls.filter((c) => c.key.startsWith('GET jobs?')).length;
  const before = listed();
  act(() =>
    push({
      type: 'jobs',
      counts: { running: 1, queued: 2 },
      active: [{ ...running, progress: 0.7 }],
    }),
  );
  expect(listed()).toBe(before);
  act(() => push({ type: 'jobs', counts: { done: 1, queued: 2 }, active: [] }));
  await vi.waitFor(() => expect(listed()).toBeGreaterThan(before));
});

it('shows running jobs on the dashboard', async () => {
  window.location.hash = '#/';
  mockApi({
    'GET auth/state': state({ authenticated: true, username: 'admin', method: 'session' }),
    'GET jobs?status=active&offset=0&limit=50': jobsPage([running], { running: 1, queued: 4 }),
  });
  render(<App />);
  expect(await screen.findByText('In progress')).toBeInTheDocument();
  expect(screen.getByText('4 more files are waiting.')).toBeInTheDocument();
  act(() =>
    push({
      type: 'jobs',
      counts: { running: 1, queued: 4 },
      active: [{ ...running, progress: 0.5, eta_seconds: 4000 }],
    }),
  );
  expect(await screen.findByText(/50% · cpu .* 1 h 07 min left/)).toBeInTheDocument();
});

it('does not open a socket on the local-network bypass', async () => {
  window.location.hash = '#/';
  mockApi({
    'GET auth/state': state({ authenticated: true, username: 'admin', method: 'bypass' }),
    'GET jobs?status=active&offset=0&limit=50': jobsPage([], {}),
  });
  render(<App />);
  expect(await screen.findByText(/Nothing is being processed/)).toBeInTheDocument();
  expect(FakeSocket.instances).toHaveLength(0);
});
