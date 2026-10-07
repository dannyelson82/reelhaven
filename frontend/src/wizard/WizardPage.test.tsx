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
  expect(await screen.findByText(/size and quality, audio, a test run/)).toBeInTheDocument();
  const saved = calls.find((c) => c.key === 'PUT libraries/4/policy');
  expect(JSON.parse(String(saved?.init?.body))).toMatchObject({
    keep_languages: ['deu'],
    keep_original: true,
  });
});
