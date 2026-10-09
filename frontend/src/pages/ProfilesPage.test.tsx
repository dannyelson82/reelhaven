import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from '../App';
import { mockApi, state } from '../test/mockApi';

const loggedIn = state({ authenticated: true, username: 'admin', method: 'session' });
const balanced = {
  id: 1,
  name: 'Balanced',
  builtin: true,
  source: 'manual',
  used_by: ['Movies'],
  updated_at: '',
  settings: {
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
  },
};

afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = '';
});

it('copies a built-in profile into a new one', async () => {
  window.location.hash = '#/profiles';
  const calls = mockApi({
    'GET auth/state': loggedIn,
    'GET profiles': { body: [balanced] },
    'POST profiles': (init) => ({
      status: 201,
      body: { ...balanced, id: 2, builtin: false, ...JSON.parse(String(init?.body)) },
    }),
  });
  render(<App />);
  expect(await screen.findByText(/HEVC \(H.265\) · 10-bit · quality 6\/10/)).toBeInTheDocument();
  expect(screen.getByText('Used by: Movies')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument(); // built-in
  await userEvent.click(screen.getByRole('button', { name: 'Copy' }));
  await userEvent.click(await screen.findByRole('switch', { name: /10-bit output/ }));
  // Quality moves in half steps.
  screen.getByRole('slider', { name: 'Quality' }).focus();
  await userEvent.keyboard('{ArrowRight}');
  await userEvent.click(screen.getByRole('button', { name: 'Save' }));
  expect(await screen.findByText('Profile "Balanced (copy)" saved.')).toBeInTheDocument();
  const post = calls.find((c) => c.key === 'POST profiles');
  expect(JSON.parse(String(post?.init?.body))).toMatchObject({
    name: 'Balanced (copy)',
    settings: { ten_bit: false, quality: 6.5 },
  });
});

it('sets up audio conversion', async () => {
  window.location.hash = '#/profiles';
  const calls = mockApi({
    'GET auth/state': loggedIn,
    'GET profiles': { body: [balanced] },
    'POST profiles': (init) => ({
      status: 201,
      body: { ...balanced, id: 2, builtin: false, ...JSON.parse(String(init?.body)) },
    }),
  });
  render(<App />);
  await userEvent.click(await screen.findByRole('button', { name: 'Copy' }));
  await userEvent.click(await screen.findByRole('combobox', { name: 'Audio' }));
  // Mantine animates the dropdown open; jsdom never finishes the animation.
  await userEvent.click(
    await screen.findByRole('option', { name: /Convert large tracks/, hidden: true }),
  );
  expect(screen.getByText('Stereo 224 · 5.1 640 kbit/s')).toBeInTheDocument(); // E-AC-3 default
  // What the bitrate means, and the chart behind a link.
  expect(screen.getAllByText('Transparent for most listeners')).toHaveLength(2); // badge and chart
  expect(screen.getByText(/Plex converts audio/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'What do the bitrates mean?' }));
  const current = screen.getByRole('row', { current: true, hidden: true }); // jsdom never finishes Mantine's animation;
  expect(current).toHaveTextContent('112 kbit/s224640Transparent for most listeners');
  await userEvent.click(screen.getByText('AAC'));
  expect(screen.getByText('Stereo 128 · 5.1 384 kbit/s')).toBeInTheDocument();
  expect(screen.getAllByText('Very good: hard to tell from the original')).toHaveLength(2);
  await userEvent.type(screen.getByLabelText(/Bitrate per channel/), '80');
  expect(screen.getByText('Stereo 160 · 5.1 480 kbit/s')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Save' }));
  expect(await screen.findAllByText('Profile "Balanced (copy)" saved.')).not.toHaveLength(0);
  const post = calls.find((c) => c.key === 'POST profiles');
  expect(JSON.parse(String(post?.init?.body)).settings).toMatchObject({
    audio: 'convert',
    audio_codec: 'aac',
    audio_kbps_per_channel: 80,
  });
});

it('mimics a file into a new profile', async () => {
  window.location.hash = '#/profiles';
  const report = {
    settings: {
      ...balanced.settings,
      quality: 8,
      audio: 'convert',
      audio_codec: 'eac3',
      audio_kbps_per_channel: 107,
    },
    sources: { codec: 'read', ten_bit: 'read', quality: 'read', audio: 'read' },
    notes: ['Encoded with x265.', 'Quality read from its settings: CRF 20.'],
    sample: {
      codec: 'hevc',
      bit_depth: 10,
      width: 1920,
      height: 1080,
      video_kbps: 4200,
      encoder: 'x265',
    },
  };
  const calls = mockApi({
    'GET auth/state': loggedIn,
    'GET profiles': { body: [balanced] },
    'GET libraries': {
      body: [{ id: 1, name: 'Movies', type: 'movies', path: '/media/Movies', file_count: 1 }],
    },
    'GET libraries/1/files?q=&problems=false&offset=0&limit=15': {
      body: {
        total: 1,
        items: [
          {
            id: 7,
            relative_path: 'Good (2020)/good.mkv',
            size: 4e9,
            status: 'ok',
            video_codec: 'hevc',
            width: 1920,
            height: 1080,
            hdr: null,
          },
        ],
      },
    },
    'GET files/7/mimic': { body: { file: 'Good (2020)/good.mkv', report } },
    'POST profiles': (init) => ({
      status: 201,
      body: { ...balanced, id: 3, builtin: false, ...JSON.parse(String(init?.body)) },
    }),
  });
  render(<App />);
  await userEvent.click(await screen.findByRole('button', { name: 'Mimic a file' }));
  await userEvent.click(await screen.findByText('good.mkv'));
  expect(await screen.findByText('Quality read from its settings: CRF 20.')).toBeInTheDocument();
  expect(
    screen.getByText(/HEVC · 10-bit · 1920×1080 · video 4.2 Mbit\/s · made with x265/),
  ).toBeInTheDocument();
  expect(screen.getByText(/quality 8\/10/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Use these settings' }));

  expect(await screen.findByText('Settings from Good (2020)/good.mkv')).toBeInTheDocument();
  expect(screen.getAllByText('read from the sample')).toHaveLength(4);
  expect(screen.getByRole('textbox', { name: 'Name' })).toHaveValue('Like good');
  await userEvent.click(screen.getByRole('button', { name: 'Save' }));
  expect(await screen.findAllByText('Profile "Like good" saved.')).not.toHaveLength(0);
  const post = calls.find((c) => c.key === 'POST profiles');
  expect(JSON.parse(String(post?.init?.body))).toMatchObject({
    name: 'Like good',
    settings: { quality: 8, audio: 'convert', audio_kbps_per_channel: 107 },
    mimic: { file: 'Good (2020)/good.mkv', sources: { quality: 'read' } },
  });
});

it('turns on downmixing with a warning', async () => {
  window.location.hash = '#/profiles';
  const calls = mockApi({
    'GET auth/state': loggedIn,
    'GET profiles': { body: [balanced] },
    'POST profiles': (init) => ({
      status: 201,
      body: { ...balanced, id: 4, builtin: false, ...JSON.parse(String(init?.body)) },
    }),
  });
  render(<App />);
  await userEvent.click(await screen.findByRole('button', { name: 'Copy' }));
  expect(screen.queryByText(/Downmix surround to stereo/)).not.toBeInTheDocument(); // audio copied
  await userEvent.click(await screen.findByRole('combobox', { name: 'Audio' }));
  await userEvent.click(
    await screen.findByRole('option', { name: /Convert large tracks/, hidden: true }),
  );
  await userEvent.click(screen.getByRole('switch', { name: /Downmix surround to stereo/ }));
  expect(screen.getByText(/every screen and speaker you watch on is stereo/)).toBeInTheDocument();
  expect(screen.getByText('Stereo 224 kbit/s')).toBeInTheDocument();
  expect(screen.queryByText(/Add a stereo AAC track/)).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Save' }));
  expect(await screen.findAllByText(/saved\./)).not.toHaveLength(0);
  const post = calls.find((c) => c.key === 'POST profiles');
  expect(JSON.parse(String(post?.init?.body)).settings).toMatchObject({
    audio: 'convert',
    downmix_stereo: true,
  });
});
