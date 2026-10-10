import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from '../App';
import { mockApi, state } from '../test/mockApi';

const loggedIn = state({ authenticated: true, username: 'admin', method: 'session' });
const job = {
  id: 4,
  library_id: 1,
  library_name: 'Movies',
  media_file_id: 9,
  file: 'Film (2020)/film.mkv',
  type: 'remux',
  status: 'failed',
  progress: 0.4,
  summary: 'Will remove 2 audio tracks.',
  details: ['Remove audio: French, German.'],
  error: 'the original file changed since it was planned; scan and try again',
  requested_by: 'admin',
  created_at: '2026-10-06T10:00:00Z',
  started_at: null,
  finished_at: null,
  bytes_before: null,
  bytes_after: null,
  process_seconds: null,
};

afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = '';
});

it('shows a failed job, reassures that nothing changed, and retries', async () => {
  window.location.hash = '#/jobs';
  const calls = mockApi({
    'GET auth/state': loggedIn,
    'GET jobs?status=all&offset=0&limit=50': {
      body: { total: 1, counts: { failed: 1 }, items: [job] },
    },
    'POST jobs/4/retry': { status: 201, body: { ...job, id: 5, status: 'queued' } },
  });
  render(<App />);
  expect(await screen.findByText('The original file was not changed')).toBeInTheDocument();
  expect(screen.getByText(/changed since it was planned/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
  expect(calls.some((c) => c.key === 'POST jobs/4/retry')).toBe(true);
});

it('shows savings for a finished job', async () => {
  window.location.hash = '#/jobs';
  mockApi({
    'GET auth/state': loggedIn,
    'GET jobs?status=all&offset=0&limit=50': {
      body: {
        total: 1,
        counts: { done: 1 },
        items: [
          {
            ...job,
            status: 'done',
            error: null,
            bytes_before: 5e9,
            bytes_after: 4.2e9,
            process_seconds: 31,
          },
        ],
      },
    },
  });
  render(<App />);
  expect(await screen.findByText(/Saved 800 MB/)).toBeInTheDocument();
});

it('restores from the recycle bin', async () => {
  window.location.hash = '#/recycle';
  const item = {
    id: 2,
    library_id: 1,
    original_path: '/media/Movies/Film (2020)/film.mkv',
    size: 5e9,
    reason: 'replaced',
    job_id: 4,
    created_at: '2026-10-06T10:00:00Z',
    expires_at: '2026-10-20T10:00:00Z',
    restored_at: null,
    purged_at: null,
  };
  const calls = mockApi({
    'GET auth/state': loggedIn,
    'GET recycle?show=active': { body: [item] },
    'POST recycle/2/restore': { body: { ...item, restored_at: '2026-10-06T11:00:00Z' } },
  });
  render(<App />);
  expect(await screen.findByText(/replaced by job #4/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Restore' }));
  expect(await screen.findByText(/Restored\. The version it replaced/)).toBeInTheDocument();
  expect(calls.some((c) => c.key === 'POST recycle/2/restore')).toBe(true);
});

it('asks before permanently deleting', async () => {
  window.location.hash = '#/recycle';
  const item = {
    id: 2,
    library_id: 1,
    original_path: '/media/Movies/film.mkv',
    size: 1e9,
    reason: 'replaced',
    job_id: 4,
    created_at: '2026-10-06T10:00:00Z',
    expires_at: '2026-10-20T10:00:00Z',
    restored_at: null,
    purged_at: null,
  };
  const calls = mockApi({
    'GET auth/state': loggedIn,
    'GET recycle?show=active': { body: [item] },
  });
  render(<App />);
  await userEvent.click(await screen.findByRole('button', { name: 'Delete' }));
  expect(await screen.findByText(/can't be undone/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Keep it' }));
  expect(calls.some((c) => c.key.startsWith('DELETE'))).toBe(false);
});

it('shows live encode progress and a no-gain result', async () => {
  window.location.hash = '#/jobs';
  const base = {
    ...job,
    type: 'encode',
    error: null,
    outcome: null,
    device: 'nvidia:0',
    fps: null,
    speed: null,
  };
  mockApi({
    'GET auth/state': loggedIn,
    'GET jobs?status=all&offset=0&limit=50': {
      body: {
        total: 2,
        counts: { running: 1, done: 1 },
        items: [
          { ...base, id: 7, status: 'running', progress: 0.42, fps: 148.2, speed: 6.1 },
          {
            ...base,
            id: 6,
            status: 'done',
            outcome: 'no_gain',
            bytes_before: 2e9,
            bytes_after: 1.95e9,
          },
        ],
      },
    },
  });
  render(<App />);
  expect(await screen.findByText(/42% · nvidia:0 · 148 fps · 6.1× real time/)).toBeInTheDocument();
  expect(screen.getByText('No gain: the original was kept')).toBeInTheDocument();
});

it('says where each encode decoded its video', async () => {
  window.location.hash = '#/jobs';
  const base = {
    ...job,
    type: 'encode',
    error: null,
    outcome: null,
    device: 'nvidia:0',
    fps: null,
    speed: null,
  };
  mockApi({
    'GET auth/state': loggedIn,
    'GET devices': {
      body: {
        detecting: false,
        detected_at: 1,
        settings: {},
        devices: [
          {
            id: 'nvidia:0',
            kind: 'nvidia',
            name: 'NVIDIA GeForce RTX 3060',
            family: 'nvenc',
            results: [],
            enabled: true,
            concurrency: 2,
          },
        ],
      },
    },
    'GET jobs?status=all&offset=0&limit=50': {
      body: {
        total: 2,
        counts: { running: 1, done: 1 },
        items: [
          { ...base, id: 7, status: 'running', progress: 0.5, fps: 140, decoder: 'gpu' },
          {
            ...base,
            id: 6,
            status: 'done',
            outcome: 'replaced',
            decoder: 'cpu',
            bytes_before: 2e9,
            bytes_after: 1e9,
            process_seconds: 60,
          },
        ],
      },
    },
  });
  render(<App />);
  // The card's name, not its id.
  expect(
    await screen.findByText(/50% · NVIDIA GeForce RTX 3060 · Decoded on GPU · 140 fps/),
  ).toBeInTheDocument();
  expect(screen.getByText(/on NVIDIA GeForce RTX 3060 \(decoded on CPU\)/)).toBeInTheDocument();
});

it('shows upcoming work and why it waits', async () => {
  window.location.hash = '#/jobs';
  const item = (file_id: number, why: string, action: string, saved: number | null) => ({
    file_id,
    relative_path: `Show/S01E0${file_id}.mkv`,
    action,
    saved,
    why,
    library_id: 1,
    library_name: 'TV Shows',
  });
  const counts = { next: 2, test_run: 1, not_automatic: 0 };
  mockApi({
    'GET auth/state': loggedIn,
    'GET jobs?status=all&offset=0&limit=50': { body: { total: 0, counts: {}, items: [] } },
    'GET upcoming?offset=0&limit=50': {
      body: {
        total: 3,
        counts,
        saved: 3e9,
        items: [
          item(1, 'next', 'encode', 2e9),
          item(2, 'next', 'quarantine', null),
          item(3, 'test_run', 'encode', 1e9),
        ],
      },
    },
    'GET upcoming?offset=0&limit=50&why=test_run': {
      body: { total: 1, counts, saved: 1e9, items: [item(3, 'test_run', 'encode', 1e9)] },
    },
  });
  render(<App />);
  await userEvent.click(await screen.findByText('Upcoming (3)'));
  expect(await screen.findByText('3 files, saving about 3.0 GB.')).toBeInTheDocument();
  expect(screen.getByText('TV Shows · Re-encode · saves about 2.0 GB')).toBeInTheDocument();
  expect(screen.getByText('TV Shows · Quarantine (wrong language)')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Waiting for a test run (1)' }));
  expect(
    await screen.findByText(/Re-encodes in this library start once a test run/),
  ).toBeInTheDocument();
  expect(screen.queryByText('Show/S01E01.mkv')).not.toBeInTheDocument();
});
