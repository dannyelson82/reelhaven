import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from '../App';
import { mockApi, state } from '../test/mockApi';

const loggedIn = state({ authenticated: true, username: 'admin', method: 'session' });
const library = {
  id: 1,
  name: 'Movies',
  type: 'movies',
  path: '/media/Movies',
  relative_path: 'Movies',
  created_at: '',
  file_count: 1,
  last_scan_at: null,
  last_scan_error: null,
  scanning: false,
};
const run = {
  id: 3,
  status: 'done',
  file: 'Big (2020)/big.mkv',
  media_file_id: 1,
  profile: {},
  profile_is_current: true,
  error: null,
  progress: 1,
  job_status: 'done',
  fps: 120,
  created_at: '',
  finished_at: '',
  approved_by: null,
  approved_at: null,
  result: {
    bytes_before: 30e9,
    bytes_after: 9e9,
    savings_percent: 70,
    min_savings_percent: 10,
    xpsnr: 38.4,
    ssim: 0.981,
    rating: 'Very good',
    frame_times: [600, 1800],
    codec: 'hevc',
    height_before: 2160,
    height_after: 2160,
    bit_depth: 10,
    hdr: 'sdr',
    device: 'nvidia:0',
    fps: 120,
    seconds: 3600,
  },
};

afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = '';
});

it('shows a finished test run and approves it', async () => {
  window.location.hash = '#/libraries/1';
  const calls = mockApi({
    'GET auth/state': loggedIn,
    'GET libraries': { body: [library] },
    'GET libraries/1/scan': { body: null },
    'GET libraries/1/files?q=&problems=false&offset=0&limit=50': { body: { total: 0, items: [] } },
    'GET libraries/1/profile': { body: { profile_id: 2 } },
    'GET profiles': { body: [] },
    'GET libraries/1/test-run': { body: run },
    'POST test-runs/3/approve': {
      body: {
        ...run,
        status: 'approved',
        approved_by: 'admin',
        approved_at: '2026-10-07T10:00:00Z',
      },
    },
  });
  render(<App />);
  await userEvent.click(await screen.findByRole('tab', { name: 'Test run' }));
  expect(await screen.findByText('Very good')).toBeInTheDocument();
  expect(screen.getByText('30.0 GB → 9.0 GB')).toBeInTheDocument();
  expect(screen.getByText('XPSNR 38.4 dB · SSIM 0.981')).toBeInTheDocument();
  expect(screen.getAllByRole('img', { name: /Original at/ })).toHaveLength(2);
  await userEvent.click(screen.getByRole('button', { name: /Looks good/ }));
  expect(await screen.findByText(/Approved\. You can now re-encode/)).toBeInTheDocument();
  expect(calls.some((c) => c.key === 'POST test-runs/3/approve')).toBe(true);
});

it('asks for a profile first', async () => {
  window.location.hash = '#/libraries/1';
  mockApi({
    'GET auth/state': loggedIn,
    'GET libraries': { body: [library] },
    'GET libraries/1/scan': { body: null },
    'GET libraries/1/files?q=&problems=false&offset=0&limit=50': { body: { total: 0, items: [] } },
    'GET libraries/1/profile': { body: { profile_id: null } },
    'GET profiles': { body: [] },
    'GET libraries/1/test-run': { body: null },
  });
  render(<App />);
  await userEvent.click(await screen.findByRole('tab', { name: 'Test run' }));
  expect(await screen.findByText(/Choose a compression profile/)).toBeInTheDocument();
});
