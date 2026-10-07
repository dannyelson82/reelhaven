import { fireEvent, render, screen } from '@testing-library/react';
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

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  window.location.hash = '';
});

it('walks a new library through folder, scan and languages', async () => {
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
  expect(await screen.findByText(/a test run and going automatic/)).toBeInTheDocument();
  const newProfile = calls.find((c) => c.key === 'POST profiles');
  expect(JSON.parse(String(newProfile?.init?.body))).toMatchObject({
    name: 'Small, smaller audio',
    settings: { quality: 4, audio: 'compress_lossless', audio_codec: 'eac3' },
  });
  const assigned = calls.find((c) => c.key === 'PUT libraries/4/profile');
  expect(JSON.parse(String(assigned?.init?.body))).toEqual({ profile_id: 9 });
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
  });
  render(<App />);
  await userEvent.click(await screen.findByRole('button', { name: 'More options' }));
  await userEvent.click(await screen.findByRole('combobox', { name: 'Use another profile' }));
  await userEvent.click(
    await screen.findByRole('option', { name: /Don't re-encode video/, hidden: true }),
  );
  await userEvent.click(screen.getByRole('button', { name: 'Next' }));
  expect(await screen.findByText(/a test run and going automatic/)).toBeInTheDocument();
  const assigned = calls.find((c) => c.key === 'PUT libraries/4/profile');
  expect(JSON.parse(String(assigned?.init?.body))).toEqual({ profile_id: null });
  expect(screen.queryByText('Audio')).not.toBeInTheDocument(); // not in the stepper
});
