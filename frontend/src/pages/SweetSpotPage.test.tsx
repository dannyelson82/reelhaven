import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from '../App';
import { mockApi, state } from '../test/mockApi';

const loggedIn = state({ authenticated: true, username: 'admin', method: 'session' });
const SETTINGS = {
  codec: 'hevc',
  quality: 6,
  speed: 'balanced',
  ten_bit: true,
  max_height: null,
  audio: 'copy',
  audio_codec: 'eac3',
  audio_kbps_per_channel: null,
  downmix_stereo: false,
  add_stereo_aac: false,
  min_savings_percent: 10,
};
const balanced = {
  id: 2,
  name: 'Balanced',
  builtin: true,
  settings: SETTINGS,
  source: 'manual',
  mimic: null,
  used_by: [],
  updated_at: '',
};
const library = { id: 4, name: 'Movies', type: 'movies', path: '/media/Movies' };
const result = (after: number, rating: string) => ({
  bytes_before: 20e9,
  bytes_after: after,
  savings_percent: Math.round(100 * (1 - after / 20e9)),
  scene_bytes_before: 1e8,
  scene_bytes_after: 1e8 * (after / 20e9),
  xpsnr: 40,
  ssim: 0.99,
  rating,
  frame_times: [5, 15, 25],
  clip: { start: 7.5, seconds: 15 },
  codec: 'hevc',
  bit_depth: 10,
  height_after: 1080,
  hdr: 'sdr',
  device: 'nvidia:0',
  fps: 200,
  seconds: 20,
});
const step = (id: number, quality: number, extra: object) => ({
  id,
  quality,
  status: 'done',
  result: null,
  error: null,
  progress: 1,
  job_id: id + 100,
  fps: null,
  ...extra,
});
const SESSION = {
  id: 7,
  file: 'Film (2020)/film.mkv',
  media_file_id: 11,
  library_id: 4,
  base: SETTINGS,
  scene_start: 2880,
  scene_seconds: 30,
  file_bytes: 20e9,
  steps: [
    step(1, 8, { result: result(12e9, 'Indistinguishable') }),
    step(2, 6, { result: result(8e9, 'Very good') }),
    step(3, 4, { status: 'running', progress: 0.4, fps: 180 }),
  ],
  created_at: '2026-10-09T10:00:00Z',
};

afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = '';
});

it('starts a session on a library file', async () => {
  window.location.hash = '#/sweet-spot';
  const calls = mockApi({
    'GET auth/state': loggedIn,
    'GET libraries': { body: [library] },
    'GET profiles': { body: [balanced] },
    'GET tune-sessions': { body: [] },
    'GET libraries/4/files?q=&problems=false&offset=0&limit=15': {
      body: {
        total: 1,
        items: [
          {
            id: 11,
            relative_path: 'Film (2020)/film.mkv',
            status: 'ok',
            video_codec: 'h264',
            width: 1920,
            height: 1080,
            hdr: null,
            size: 20e9,
          },
        ],
      },
    },
    'POST tune-sessions': { status: 201, body: SESSION },
    'GET tune-sessions/7': { body: SESSION },
  });
  render(<App />);
  expect(await screen.findByText(/HEVC \(H.265\) · 10-bit · keep resolution/)).toBeInTheDocument();
  await userEvent.click(await screen.findByText('film.mkv'));
  await userEvent.click(screen.getByRole('button', { name: 'Encode three versions' }));
  const post = calls.find((c) => c.key === 'POST tune-sessions');
  expect(JSON.parse(String(post?.init?.body))).toEqual({ file_id: 11, settings: SETTINGS });
  expect(await screen.findByText('Quality 8')).toBeInTheDocument();
  expect(window.location.hash).toContain('session=7');
});

it('compares, dials in and keeps a version', async () => {
  window.location.hash = '#/sweet-spot?session=7&from=wizard&library=4';
  const calls = mockApi({
    'GET auth/state': loggedIn,
    'GET tune-sessions/7': { body: SESSION },
    'POST tune-sessions/7/steps': {
      status: 201,
      body: { ...SESSION, steps: [...SESSION.steps, step(4, 7, { status: 'queued' })] },
    },
    'GET devices': {
      body: {
        detecting: false,
        detected_at: 1,
        devices: [{ id: 'nvidia:0', name: 'RTX 3060' }],
        settings: {},
      },
    },
    'POST profiles': (init) => ({
      status: 201,
      body: { ...balanced, id: 9, builtin: false, ...JSON.parse(String(init?.body)) },
    }),
  });
  render(<App />);
  expect(await screen.findByText('≈ 12.0 GB')).toBeInTheDocument();
  expect(screen.getByText('Saves about 12.0 GB (60%)')).toBeInTheDocument();
  expect(screen.getByText('(Balanced)')).toBeInTheDocument();
  expect(screen.getByText('40% · 180 fps')).toBeInTheDocument(); // still encoding

  // Compare one with the original, stills and clips.
  await userEvent.click(screen.getAllByRole('button', { name: 'Compare' })[1]);
  const viewer = await screen.findByRole('dialog');
  expect(within(viewer).getAllByRole('img')[1]).toHaveAttribute(
    'src',
    'api/v1/tune-steps/2/frames/0/encoded',
  );
  await userEvent.click(within(viewer).getByText('Video'));
  expect(within(viewer).getByLabelText('Quality 6 clip')).toHaveAttribute(
    'src',
    'api/v1/tune-steps/2/clips/encoded',
  );
  expect(within(viewer).getByText('48:08 in the film')).toBeInTheDocument();
  await userEvent.keyboard('{Escape}');

  // Dial in: the one between 8 and 6.
  await userEvent.click(await screen.findByRole('button', { name: 'Between 8 and 6: 7' }));
  const added = calls.find((c) => c.key === 'POST tune-sessions/7/steps');
  expect(JSON.parse(String(added?.init?.body))).toEqual({ quality: 7 });
  expect(await screen.findByText('Waiting for a free graphics card…')).toBeInTheDocument();

  // Keep one as a profile, then back to the wizard with it chosen.
  await userEvent.click(screen.getAllByRole('button', { name: 'Keep this' })[1]);
  const keep = await screen.findByRole('dialog');
  expect(within(keep).getByLabelText('Name')).toHaveValue('Sweet spot 6 (film)');
  await userEvent.click(within(keep).getByRole('button', { name: 'Save profile' }));
  const saved = calls.find((c) => c.key === 'POST profiles');
  expect(JSON.parse(String(saved?.init?.body))).toEqual({
    name: 'Sweet spot 6 (film)',
    settings: { ...SETTINGS, quality: 6 },
  });
  expect(await within(keep).findByRole('link', { name: 'Back to the wizard' })).toHaveAttribute(
    'href',
    '#/wizard?library=4&step=quality&choice=9',
  );
});
