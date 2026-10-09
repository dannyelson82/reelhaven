import { render, screen, within } from '@testing-library/react';
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
const result = {
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
};
const sample = {
  id: 5,
  file: 'Big (2020)/big.mkv',
  media_file_id: 1,
  status: 'done',
  result,
  error: null,
  progress: 1,
  job_id: 9,
  job_status: 'done',
  fps: 120,
};
const run = {
  id: 3,
  status: 'done',
  profile: {},
  profile_is_current: true,
  samples: [sample],
  created_at: '',
  finished_at: '',
  approved_by: null,
  approved_at: null,
};
const page = {
  'GET auth/state': loggedIn,
  'GET libraries': { body: [library] },
  'GET libraries/1/scan': { body: null },
  'GET libraries/1/files?q=&problems=false&offset=0&limit=50': { body: { total: 0, items: [] } },
  'GET libraries/1/profile': { body: { profile_id: 2 } },
  'GET profiles': { body: [] },
};

afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = '';
});

it('shows a finished test run and approves it', async () => {
  window.location.hash = '#/libraries/1';
  const calls = mockApi({
    ...page,
    'GET libraries/1/test-run': { body: { samples: 1, run } },
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
  // One moment at a time inline; the row of times picks another.
  expect(screen.getByRole('img', { name: /Original at/ })).toHaveAttribute(
    'src',
    'api/v1/test-run-samples/5/frames/0/source',
  );
  await userEvent.click(screen.getByText('30:00'));
  expect(screen.getByRole('img', { name: /Re-encoded at/ })).toHaveAttribute(
    'src',
    'api/v1/test-run-samples/5/frames/1/encoded',
  );
  expect(screen.queryByText('Weakest quality')).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: /Looks good/ }));
  expect(await screen.findByText(/Approved\. You can now re-encode/)).toBeInTheDocument();
  expect(calls.some((c) => c.key === 'POST test-runs/3/approve')).toBe(true);
});

it('tests several files and sums them up', async () => {
  window.location.hash = '#/libraries/1';
  const other = {
    ...sample,
    id: 6,
    file: 'Small (2021)/small.mkv',
    result: { ...result, bytes_before: 10e9, bytes_after: 1e9, rating: 'Good' },
  };
  const failed = {
    ...sample,
    id: 7,
    file: 'Odd (2022)/odd.mkv',
    status: 'failed',
    result: null,
    error: 'Cancelled.',
  };
  const calls = mockApi({
    ...page,
    'GET libraries/1/test-run': {
      body: { samples: 3, run: { ...run, status: 'failed', samples: [sample, other, failed] } },
    },
    'POST libraries/1/test-run': { status: 201, body: run },
  });
  render(<App />);
  await userEvent.click(await screen.findByRole('tab', { name: 'Test run' }));
  expect(await screen.findByText('40.0 GB → 10.0 GB')).toBeInTheDocument();
  expect(screen.getByText('75.0%')).toBeInTheDocument();
  expect(screen.getByText('Weakest quality')).toBeInTheDocument();
  expect(screen.getByText(/1 of 3 files could not be test-encoded/)).toBeInTheDocument();
  expect(screen.getByText('Odd (2022)/odd.mkv failed')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Looks good/ })).not.toBeInTheDocument();

  expect(screen.getByRole('radio', { name: '3' })).toBeChecked(); // the library's last choice
  await userEvent.click(screen.getByText('5'));
  await userEvent.click(screen.getByRole('button', { name: 'Start a new test run' }));
  const post = calls.find((c) => c.key === 'POST libraries/1/test-run');
  expect(JSON.parse(String(post?.init?.body))).toEqual({ samples: 5 });
});

it('asks for a profile first', async () => {
  window.location.hash = '#/libraries/1';
  mockApi({
    ...page,
    'GET libraries/1/profile': { body: { profile_id: null } },
    'GET libraries/1/test-run': { body: { samples: 1, run: null } },
  });
  render(<App />);
  await userEvent.click(await screen.findByRole('tab', { name: 'Test run' }));
  expect(await screen.findByText(/Choose a compression profile/)).toBeInTheDocument();
});

it('compares stills full screen', async () => {
  window.location.hash = '#/libraries/1';
  mockApi({ ...page, 'GET libraries/1/test-run': { body: { samples: 1, run } } });
  render(<App />);
  await userEvent.click(await screen.findByRole('tab', { name: 'Test run' }));
  await userEvent.click(await screen.findByRole('button', { name: 'Compare full screen' }));
  const dialog = await screen.findByRole('dialog');
  const images = within(dialog).getAllByRole('img');
  expect(images.map((img) => img.getAttribute('src'))).toEqual([
    'api/v1/test-run-samples/5/frames/0/source',
    'api/v1/test-run-samples/5/frames/0/encoded',
  ]);
  expect(within(dialog).getByText('Loading full-size stills…')).toBeInTheDocument();

  // The arrow keys switch moments; S switches to the swipe view with its divider.
  await userEvent.keyboard('{ArrowRight}');
  expect(within(dialog).getAllByRole('img')[0]).toHaveAttribute(
    'src',
    'api/v1/test-run-samples/5/frames/1/source',
  );
  await userEvent.keyboard('s');
  const divider = within(dialog).getByRole('slider', { name: 'Divider' });
  expect(divider).toHaveAttribute('aria-valuenow', '50');
  divider.focus();
  await userEvent.keyboard('{ArrowLeft}');
  expect(divider).toHaveAttribute('aria-valuenow', '45');
});
