import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from '../App';
import { mockApi, state } from '../test/mockApi';

const loggedIn = state({ authenticated: true, username: 'admin', method: 'session' });
const library = {
  id: 4,
  name: 'TV Shows',
  type: 'tv',
  path: '/media/TV Shows',
  relative_path: 'TV Shows',
  created_at: '',
  file_count: 12,
  last_scan_at: '2026-10-08T10:00:00Z',
  last_scan_error: null,
  scanning: false,
  watch_mode: 'off',
};
const policy = {
  keep_languages: ['eng'],
  keep_original: true,
  keep_subtitles_full: true,
  keep_subtitles_forced: true,
  keep_subtitles_sdh: true,
  keep_commentary: true,
  untagged: 'keep',
  set_defaults: true,
  wrong_language_action: 'flag',
};

const SETTINGS = {
  codec: 'hevc',
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
const PROFILES = [
  ['High quality', 8],
  ['Balanced', 6],
  ['Small', 4],
].map(([name, quality], i) => ({
  id: i + 1,
  name,
  builtin: true,
  settings: { ...SETTINGS, quality },
  source: 'manual',
  mimic: null,
  used_by: [],
  updated_at: '',
}));

const sample = (id: number, file: string) => ({
  id,
  file,
  media_file_id: id,
  status: 'done',
  error: null,
  progress: 1,
  job_id: id + 100,
  job_status: 'done',
  fps: 90,
  result: {
    bytes_before: 20e9,
    bytes_after: 6e9,
    savings_percent: 70,
    min_savings_percent: 10,
    xpsnr: 38,
    ssim: 0.98,
    rating: 'Very good',
    frame_times: [600],
    codec: 'hevc',
    height_before: 1080,
    height_after: 1080,
    bit_depth: 10,
    hdr: 'sdr',
    device: 'nvidia:0',
    fps: 90,
    seconds: 300,
  },
});
const DONE_RUN = {
  id: 3,
  status: 'done',
  profile: {},
  profile_is_current: true,
  samples: [sample(5, 'Show/S01E01.mkv'), sample(6, 'Show/S01E02.mkv')],
  created_at: '',
  finished_at: '',
  approved_by: null,
  approved_at: null,
};
const DRY = {
  unchanged: 0,
  unreadable: 0,
  flags: {},
  unknown_original: 0,
  savings_unknown: 0,
  total: 0,
  items: [],
};

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  window.location.hash = '';
});

it('walks a new library from folder to automatic', async () => {
  let testRun: unknown = null;
  vi.spyOn(navigator, 'languages', 'get').mockReturnValue(['de-DE', 'en']);
  window.location.hash = '#/wizard';
  const calls = mockApi({
    'GET auth/state': loggedIn,
    'GET libraries': { body: [library] },
    'GET browse?path=': {
      body: {
        path: '',
        parent: null,
        truncated: false,
        dirs: [{ name: 'TV Shows', path: 'TV Shows' }],
      },
    },
    'GET browse?path=TV%20Shows': {
      body: { path: 'TV Shows', parent: '', truncated: false, dirs: [] },
    },
    'POST libraries': { status: 201, body: library },
    'GET libraries/4/scan': { body: null },
    'GET languages': {
      body: [
        { code: 'eng', name: 'English', alpha2: 'en' },
        { code: 'deu', name: 'German', alpha2: 'de' },
      ],
    },
    'GET libraries/4/policy': { body: policy },
    'PUT libraries/4/policy': (init) => ({ body: JSON.parse(String(init?.body)) }),
    'GET libraries/4/test-run': () => ({ body: { samples: 1, run: testRun } }),
    'POST libraries/4/test-run': () => {
      testRun = DONE_RUN;
      return { status: 201, body: DONE_RUN };
    },
    'POST test-runs/3/approve': () => {
      testRun = { ...DONE_RUN, status: 'approved' };
      return { body: testRun };
    },
    'GET devices': {
      body: { devices: [], settings: {}, detected_at: null, detecting: false },
    },
    'GET libraries/4/profile': { body: { profile_id: 9 } },
    'GET libraries/4/dry-run?show=changes&offset=0&limit=100': {
      body: { ...DRY, files: 12, encode: 10, remux: 2, saved_bytes: 50e9 },
    },
    'PATCH libraries/4': { body: { ...library, watch_mode: 'automatic' } },
    'GET onboarding': { body: { wizard_seen: false, server_steps_done: true } },
    'GET settings/recycle': { body: { keep_days: 14 } },
    'PUT settings/recycle': (init) => ({ body: JSON.parse(String(init?.body)) }),
    'PUT onboarding': (init) => ({ body: JSON.parse(String(init?.body)) }),
    'GET profiles': { body: PROFILES },
    'POST libraries/4/estimate': (init) => {
      const { profiles } = JSON.parse(String(init?.body)) as {
        profiles: Record<string, { quality: number; audio: string; downmix_stereo: boolean }>;
      };
      const results = Object.fromEntries(
        Object.entries(profiles).map(([key, s]) => [
          key,
          {
            files: 12,
            encode: 12,
            remux: 0,
            savings_unknown: 0,
            saved_bytes:
              (100 - s.quality * 10 + (s.audio === 'copy' ? 0 : s.downmix_stereo ? 11 : 8)) * 1e9,
          },
        ]),
      );
      return { body: { library_bytes: 100e9, results } };
    },
    'POST profiles': (init) => ({
      status: 201,
      body: { ...PROFILES[1], id: 9, builtin: false, ...JSON.parse(String(init?.body)) },
    }),
    'PUT libraries/4/profile': { body: { profile_id: 9 } },
  });
  render(<App />);

  // Folder: name and type are guessed from the folder.
  fireEvent.click(await screen.findByText('TV Shows'));
  expect(await screen.findByDisplayValue('TV Shows')).toBeInTheDocument();
  expect(screen.getByRole('radio', { name: 'TV shows' })).toBeChecked();
  await userEvent.click(screen.getByRole('button', { name: 'Next' }));
  const created = calls.find((c) => c.key === 'POST libraries');
  expect(JSON.parse(String(created?.init?.body))).toEqual({
    name: 'TV Shows',
    type: 'tv',
    path: 'TV Shows',
  });
  expect(window.location.hash).toContain('library=4');

  // Read files: already scanned, so it just reports.
  expect(await screen.findByText('Found 12 video files in TV Shows.')).toBeInTheDocument();
  expect(calls.some((c) => c.key === 'POST libraries/4/scan')).toBe(false);
  await userEvent.click(screen.getByRole('button', { name: 'Next' }));

  // Languages: German from the browser; English (the untouched default) is replaced.
  expect(await screen.findByDisplayValue('German')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Next' }));
  const saved = calls.find((c) => c.key === 'PUT libraries/4/policy');
  expect(JSON.parse(String(saved?.init?.body))).toMatchObject({
    keep_languages: ['deu'],
    keep_original: true,
  });

  // Size and quality: three cards with estimates; Balanced is preselected.
  expect(await screen.findByText('Saves about 60.0 GB (60%)')).toBeInTheDocument(); // Smallest
  expect(screen.getByRole('button', { name: /Balanced.*Chosen/s })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
  await userEvent.click(screen.getByRole('button', { name: /Smallest/ }));
  await userEvent.click(screen.getByRole('button', { name: 'Next' }));

  // Audio: the extra saving of each option, compared with keeping audio.
  expect(await screen.findByText('About 8.0 GB more')).toBeInTheDocument(); // shrink
  expect(screen.getByText('About 11.0 GB more')).toBeInTheDocument(); // stereo
  await userEvent.click(screen.getByRole('button', { name: /Shrink big audio tracks/ }));
  await userEvent.click(screen.getByRole('button', { name: 'Next' }));
  // Try it: a 2-file test run starts by itself; approving moves on.
  expect(await screen.findByText(/tries your choice on 2 of your files/)).toBeInTheDocument();
  const newProfile = calls.find((c) => c.key === 'POST profiles');
  expect(JSON.parse(String(newProfile?.init?.body))).toMatchObject({
    name: 'Small, smaller audio',
    settings: { quality: 4, audio: 'compress_lossless', audio_codec: 'eac3' },
  });
  const assigned = calls.find((c) => c.key === 'PUT libraries/4/profile');
  expect(JSON.parse(String(assigned?.init?.body))).toEqual({ profile_id: 9 });

  const startRun = calls.find((c) => c.key === 'POST libraries/4/test-run');
  expect(JSON.parse(String(startRun?.init?.body))).toEqual({ samples: 2 });
  expect(await screen.findAllByText('20.0 GB → 6.0 GB (70% smaller)')).toHaveLength(2);
  expect(screen.getAllByRole('img', { name: 'Original' })).toHaveLength(2);
  await userEvent.click(screen.getAllByRole('button', { name: /Look closer/ })[0]);
  const viewer = await screen.findByRole('dialog');
  expect(within(viewer).getByRole('img', { name: 'Smaller at 10:00' })).toBeInTheDocument();
  await userEvent.keyboard('{Escape}');
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  await userEvent.click(screen.getByRole('button', { name: 'Looks good' }));
  expect(calls.some((c) => c.key === 'POST test-runs/3/approve')).toBe(true);

  // Safety net: turning the recycle bin off needs a confirmation.
  expect(await screen.findByText(/How long should originals be kept/)).toBeInTheDocument();
  await userEvent.click(screen.getByText('Off'));
  expect(screen.getByText('No undo')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
  await userEvent.click(screen.getByRole('checkbox', { name: /can't be put back/ }));
  await userEvent.click(screen.getByRole('button', { name: 'Next' }));
  const kept = calls.find((c) => c.key === 'PUT settings/recycle');
  expect(JSON.parse(String(kept?.init?.body))).toEqual({ keep_days: 0 });

  // Go automatic.
  expect(await screen.findByText('12 files need work, saving about 50.0 GB.')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Start' }));
  const patch = calls.find((c) => c.key === 'PATCH libraries/4');
  expect(JSON.parse(String(patch?.init?.body))).toEqual({ watch_mode: 'automatic' });
  expect(await screen.findByText('TV Shows is set up.')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'See the progress' })).toHaveAttribute('href', '#/jobs');
  expect(JSON.parse(String(calls.find((c) => c.key === 'PUT onboarding')?.init?.body))).toEqual({
    wizard_seen: true,
    server_steps_done: true,
  });
});

it('skips the audio step when video is not re-encoded', async () => {
  window.location.hash = '#/wizard?library=4&step=quality';
  const calls = mockApi({
    'GET auth/state': loggedIn,
    'GET libraries': { body: [library] },
    'GET profiles': { body: PROFILES },
    'POST libraries/4/estimate': {
      body: { library_bytes: 1e9, results: {} },
    },
    'PUT libraries/4/profile': { body: { profile_id: null } },
    'GET libraries/4/dry-run?show=changes&offset=0&limit=100': {
      body: { ...DRY, files: 3, encode: 0, remux: 2, saved_bytes: 1e9 },
    },
    'GET settings/recycle': { body: { keep_days: 14 } },
    'GET onboarding': { body: { wizard_seen: true, server_steps_done: true } },
  });
  render(<App />);
  await userEvent.click(await screen.findByRole('button', { name: 'More options' }));
  await userEvent.click(await screen.findByRole('combobox', { name: 'Use another profile' }));
  await userEvent.click(
    await screen.findByRole('option', { name: /Don't re-encode video/, hidden: true }),
  );
  await userEvent.click(screen.getByRole('button', { name: 'Next' }));
  await screen.findByText(/How long should originals be kept/); // safety net, unchanged
  await userEvent.click(screen.getByRole('button', { name: 'Next' }));
  expect(await screen.findByText(/Last step/)).toBeInTheDocument(); // no audio, no test run
  expect(await screen.findByText('2 files need work, saving about 1.0 GB.')).toBeInTheDocument();
  const assigned = calls.find((c) => c.key === 'PUT libraries/4/profile');
  expect(JSON.parse(String(assigned?.init?.body))).toEqual({ profile_id: null });
  expect(screen.queryByText('Try it')).not.toBeInTheDocument();
  expect(screen.queryByText('Audio')).not.toBeInTheDocument(); // not in the stepper
});

const reading = (probed: number) => ({
  state: 'scanning',
  phase: 'probing',
  found: 3000,
  to_match: 0,
  matched: 0,
  to_probe: 3000,
  probed,
  failed: 0,
  unchanged: 0,
  moved: 0,
  removed: 0,
  unstable: 0,
  languages_resolved: 0,
  languages_unknown: 0,
  language_errors: [],
  folders: [],
  error: null,
  started_at: 0,
  phase_started_at: 0,
  finished_at: null,
  eta_seconds: 1500,
});

it('goes on while the library is still being read', async () => {
  window.location.hash = '#/wizard?library=4&step=scan';
  mockApi({
    'GET auth/state': loggedIn,
    'GET libraries': { body: [{ ...library, last_scan_at: null, scanning: true, file_count: 40 }] },
    'GET libraries/4/scan': { body: reading(40) },
    'GET onboarding': { body: { wizard_seen: true, server_steps_done: true } },
  });
  render(<App />);
  expect(await screen.findByText('Reading files: 40 of 3,000')).toBeInTheDocument();
  expect(screen.getByText('about 25 min left')).toBeInTheDocument();
  expect(screen.getByText(/You don't need to wait/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Next' })).toBeEnabled();
});

it('estimates from the files read so far, scaled to the whole library', async () => {
  window.location.hash = '#/wizard?library=4&step=quality';
  let probed = 50;
  const results = Object.fromEntries(
    PROFILES.map((p) => [
      String(p.id),
      { files: probed, encode: probed, remux: 0, savings_unknown: 0, saved_bytes: 4e9 },
    ]),
  );
  mockApi({
    'GET auth/state': loggedIn,
    'GET libraries': { body: [library] },
    'GET profiles': { body: PROFILES },
    'GET libraries/4/scan': () => ({ body: reading(probed) }),
    // 10 GB read so far of 100 GB found: savings scale by 10.
    'POST libraries/4/estimate': () => ({
      body: {
        library_bytes: 10e9,
        results,
        reading: { probed, to_probe: 3000, found_bytes: 100e9 },
      },
    }),
    'GET onboarding': { body: { wizard_seen: true, server_steps_done: true } },
  });
  const { unmount } = render(<App />);
  expect(await screen.findByText(/estimates appear once the first 200/)).toBeInTheDocument();
  expect(screen.queryByText(/Saves about/)).not.toBeInTheDocument();
  unmount();

  probed = 300;
  render(<App />);
  expect((await screen.findAllByText('Saves about 40.0 GB (40%)')).length).toBe(3);
  expect(screen.getByText(/Estimated from 300 of 3,000 files read so far/)).toBeInTheDocument();
});

it('copies a file the owner likes', async () => {
  window.location.hash = '#/wizard?library=4&step=quality';
  const liked = { ...SETTINGS, quality: 5, audio: 'convert', audio_kbps_per_channel: 96 };
  const profiles = [...PROFILES];
  const calls = mockApi({
    'GET auth/state': loggedIn,
    'GET libraries': { body: [library] },
    'GET profiles': () => ({ body: profiles }),
    'POST libraries/4/estimate': (init) => {
      const asked = Object.keys(JSON.parse(String(init?.body)).profiles);
      const results = Object.fromEntries(
        asked.map((key) => [key, { saved_bytes: key === 'mimic' ? 4e9 : 2e9, files: 12 }]),
      );
      return { body: { library_bytes: 10e9, results } };
    },
    'GET libraries/4/files?q=&problems=false&offset=0&limit=15': {
      body: {
        total: 1,
        items: [
          {
            id: 77,
            relative_path: 'Show/S02E01.mkv',
            status: 'ok',
            video_codec: 'hevc',
            width: 1920,
            height: 1080,
            hdr: null,
            size: 2e9,
          },
        ],
      },
    },
    'GET files/77/mimic': {
      body: {
        file: 'TV Shows/Show/S02E01.mkv',
        report: {
          settings: liked,
          sources: { quality: 'estimated' },
          notes: ['Quality estimated from the video bitrate.'],
          sample: { codec: 'hevc', bit_depth: 10, width: 1920, height: 1080, video_kbps: 4000 },
        },
      },
    },
    'POST profiles': (init) => {
      const created = { ...PROFILES[0], id: 9, builtin: false, ...JSON.parse(String(init?.body)) };
      profiles.push(created);
      return { status: 201, body: created };
    },
    'GET settings/recycle': { body: { keep_days: 14 } },
    'GET onboarding': { body: { wizard_seen: true, server_steps_done: true } },
  });
  render(<App />);
  await userEvent.click(await screen.findByRole('button', { name: /Copy a file I like/ }));
  // The picker shows only this library's files, then what was read and what it would save.
  expect(screen.queryByLabelText('Library')).not.toBeInTheDocument();
  await userEvent.click(await screen.findByText('S02E01.mkv'));
  expect(await screen.findByText('Quality estimated from the video bitrate.')).toBeInTheDocument();
  expect(await screen.findByText('Saves about 4.0 GB (40%)')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Choose this' }));

  const card = await screen.findByRole('button', { name: /Copy a file I like.*Chosen/s });
  expect(card).toHaveTextContent('Like S02E01.mkv');
  expect(card).toHaveTextContent('Saves about 4.0 GB (40%)');
  await userEvent.click(screen.getByRole('button', { name: 'Next' }));

  // Next saved it as a profile; the audio step offers its own audio first.
  expect(await screen.findByText('As set in this profile')).toBeInTheDocument();
  const post = calls.find((c) => c.key === 'POST profiles');
  expect(JSON.parse(String(post?.init?.body))).toMatchObject({
    name: 'Like S02E01',
    settings: liked,
    mimic: { file: 'TV Shows/Show/S02E01.mkv' },
  });
});
