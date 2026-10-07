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
