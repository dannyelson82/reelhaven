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
  last_scan_at: '2026-10-06T10:00:00Z',
  last_scan_error: null,
  scanning: false,
};
const file = {
  id: 7,
  relative_path: 'Amélie (2001)/Amélie.mkv',
  size: 4_200_000_000,
  status: 'ok',
  duration_s: 7320,
  video_codec: 'hevc',
  width: 1920,
  height: 1080,
  hdr: 'hdr10',
  audio_languages: ['fra', 'eng'],
  subtitle_languages: ['eng', null],
  probe_error: null,
  title_id: 2,
  original_language: 'fra',
  language_source: 'radarr',
};

afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = '';
});

it('lists files with languages and opens stream details', async () => {
  window.location.hash = '#/libraries/1';
  mockApi({
    'GET auth/state': loggedIn,
    'GET libraries': { body: [library] },
    'GET libraries/1/scan': { body: null },
    'GET libraries/1/files?q=&problems=false&offset=0&limit=50': {
      body: { total: 1, items: [file] },
    },
    'GET languages': { body: [{ code: 'fra', name: 'French' }] },
    'GET files/7/plan': {
      body: {
        action: 'remux',
        tracks: [],
        flags: ['dolby_vision'],
        summary: 'Original language: French. Will remove 1 audio track.',
        details: ['Remove audio: German.'],
        removed_bytes: 300_000_000,
      },
    },
    'GET files/7': {
      body: {
        ...file,
        path: '/media/Movies/Amélie (2001)/Amélie.mkv',
        container: 'matroska,webm',
        bit_rate: 5_000_000,
        probed_at: null,
        streams: [
          {
            index: 0,
            kind: 'video',
            codec: 'hevc',
            width: 1920,
            height: 1080,
            bit_depth: 10,
            hdr: 'hdr10',
            language: null,
            default: true,
            forced: false,
            hearing_impaired: false,
            commentary: false,
            image_based: false,
          },
          {
            index: 1,
            kind: 'audio',
            codec: 'dts',
            language: 'fra',
            title: 'Français',
            channel_layout: '5.1',
            default: true,
            forced: false,
            hearing_impaired: false,
            commentary: false,
            image_based: false,
          },
          {
            index: 2,
            kind: 'subtitle',
            codec: 'subrip',
            language: 'eng',
            title: 'Forced',
            default: false,
            forced: true,
            hearing_impaired: false,
            commentary: false,
            image_based: false,
          },
        ],
      },
    },
  });
  render(<App />);
  expect(await screen.findByText('Amélie.mkv')).toBeInTheDocument();
  expect(screen.getAllByText('French')).toHaveLength(2); // original + audio track
  expect(screen.getByText('Untagged')).toBeInTheDocument();
  expect(screen.getByText('HDR10')).toBeInTheDocument();
  expect(screen.getByText('1080p')).toBeInTheDocument();
  expect(screen.getByText('4.2 GB')).toBeInTheDocument();

  await userEvent.click(screen.getByText('Amélie.mkv'));
  expect(await screen.findByText('Français')).toBeInTheDocument();
  expect(screen.getByText('forced')).toBeInTheDocument();
  expect(screen.getByText(/2:02:00/)).toBeInTheDocument();
  expect(screen.getByText('(Radarr)')).toBeInTheDocument();
  expect(
    await screen.findByText('Will remove 1 audio track.', { exact: false }),
  ).toBeInTheDocument();
  expect(screen.getByText('Remove audio: German.')).toBeInTheDocument();
  // The language editor and the plan summary both name the original language.
  expect(screen.getAllByText(/Original language: French/)).toHaveLength(2);
  expect(screen.getByText('Dolby Vision')).toBeInTheDocument();
  expect(screen.getByText('Saves about 300 MB.')).toBeInTheDocument();
});

it('invites a first scan', async () => {
  window.location.hash = '#/libraries/1';
  mockApi({
    'GET auth/state': loggedIn,
    'GET libraries': { body: [{ ...library, file_count: 0, last_scan_at: null }] },
    'GET libraries/1/scan': { body: null },
    'GET libraries/1/files?q=&problems=false&offset=0&limit=50': { body: { total: 0, items: [] } },
  });
  render(<App />);
  expect(await screen.findByText(/Click "Scan library"/)).toBeInTheDocument();
});

it('edits the language policy', async () => {
  window.location.hash = '#/libraries/1';
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
  const calls = mockApi({
    'GET auth/state': loggedIn,
    'GET libraries': { body: [library] },
    'GET libraries/1/scan': { body: null },
    'GET libraries/1/files?q=&problems=false&offset=0&limit=50': { body: { total: 0, items: [] } },
    'GET libraries/1/policy': { body: policy },
    'GET languages': { body: [{ code: 'eng', name: 'English' }] },
    'PUT libraries/1/policy': (init) => ({ body: JSON.parse(String(init?.body)) }),
  });
  render(<App />);
  await userEvent.click(await screen.findByRole('button', { name: 'Language policy' }));
  await userEvent.click(await screen.findByLabelText('Keep commentary tracks'));
  await userEvent.click(screen.getByRole('button', { name: 'Save' }));
  expect(await screen.findByText('Language policy saved.')).toBeInTheDocument();
  const put = calls.find((c) => c.key === 'PUT libraries/1/policy');
  expect(JSON.parse(String(put?.init?.body))).toMatchObject({
    keep_commentary: false,
    keep_languages: ['eng'],
  });
});

it('applies a dry run with the confirmed number of files', async () => {
  window.location.hash = '#/libraries/1';
  const report = {
    files: 3,
    encode: 0,
    remux: 2,
    unchanged: 1,
    unreadable: 0,
    flags: {},
    unknown_original: 0,
    saved_bytes: 1e9,
    savings_unknown: 0,
    total: 2,
    items: [
      {
        file_id: 1,
        relative_path: 'A/a.mkv',
        size: 1,
        original_language: 'eng',
        action: 'remux',
        flags: [],
        summary: 's',
        details: ['Remove audio: French.'],
        removed_bytes: 5e8,
      },
      {
        file_id: 2,
        relative_path: 'B/b.mkv',
        size: 1,
        original_language: 'eng',
        action: 'remux',
        flags: [],
        summary: 's',
        details: ['Remove audio: German.'],
        removed_bytes: 5e8,
      },
    ],
  };
  const calls = mockApi({
    'GET auth/state': loggedIn,
    'GET libraries': { body: [library] },
    'GET libraries/1/scan': { body: null },
    'GET libraries/1/files?q=&problems=false&offset=0&limit=50': { body: { total: 0, items: [] } },
    'GET libraries/1/dry-run?show=changes&offset=0&limit=100': { body: report },
    'POST libraries/1/apply': { body: { queued: 2 } },
  });
  render(<App />);
  await userEvent.click(await screen.findByRole('tab', { name: 'Dry run' }));
  await userEvent.click(await screen.findByRole('button', { name: 'Run dry run' }));
  await userEvent.click(await screen.findByRole('button', { name: 'Apply to 2 files' }));
  expect(await screen.findByText(/Originals go to the recycle bin/)).toBeInTheDocument();
  const dialog = await screen.findByRole('dialog');
  await userEvent.click(
    Array.from(dialog.querySelectorAll('button')).find(
      (b) => b.textContent === 'Apply to 2 files',
    )!,
  );
  expect(await screen.findByText(/2 files queued/)).toBeInTheDocument();
  const post = calls.find((c) => c.key === 'POST libraries/1/apply');
  expect(JSON.parse(String(post?.init?.body))).toEqual({ expected_count: 2 });
});
