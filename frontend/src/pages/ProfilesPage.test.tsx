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
  await userEvent.click(screen.getByRole('button', { name: 'Save' }));
  expect(await screen.findByText('Profile "Balanced (copy)" saved.')).toBeInTheDocument();
  const post = calls.find((c) => c.key === 'POST profiles');
  expect(JSON.parse(String(post?.init?.body))).toMatchObject({
    name: 'Balanced (copy)',
    settings: { ten_bit: false, quality: 6 },
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
  await userEvent.click(screen.getByText('AAC'));
  expect(screen.getByText('Stereo 128 · 5.1 384 kbit/s')).toBeInTheDocument();
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
