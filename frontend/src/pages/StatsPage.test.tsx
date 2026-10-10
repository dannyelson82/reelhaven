import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from '../App';
import { mockApi, state } from '../test/mockApi';

const loggedIn = state({ authenticated: true, username: 'admin', method: 'session' });
const days = Array.from({ length: 30 }, (_, i) => ({
  day: `2026-09-${String(i + 1).padStart(2, '0')}`,
  encoded: i === 29 ? 3 : 0,
  remuxed: 0,
  failed: 0,
  saved: 0,
}));
const performance = {
  devices: [
    {
      device: 'nvidia:0',
      files: 120,
      failed: 2,
      saved: 800e9,
      video_hours: 240,
      work_hours: 30,
      speed: 8,
      fps: 190.4,
      gpu_decoded: 0.96,
    },
  ],
  daily: days,
};

afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = '';
});

it('shows each device and lets the period change', async () => {
  window.location.hash = '#/stats';
  const calls = mockApi({
    'GET auth/state': loggedIn,
    'GET stats/performance?days=30': { body: performance },
    'GET stats/performance?days=0': { body: { ...performance, devices: [] } },
    'GET stats/savings': {
      body: {
        total_saved: 0,
        files: 0,
        this_week: 0,
        this_month: 0,
        weekly: [],
        monthly: [],
        libraries: [],
      },
    },
    'GET devices': {
      body: {
        detecting: false,
        detected_at: 1,
        devices: [{ id: 'nvidia:0', name: 'NVIDIA GeForce RTX 3060' }],
        settings: {},
      },
    },
  });
  render(<App />);
  expect(await screen.findByText('NVIDIA GeForce RTX 3060')).toBeInTheDocument();
  expect(screen.getByText('8.0× real time')).toBeInTheDocument();
  expect(screen.getByText('190 fps')).toBeInTheDocument();
  expect(screen.getByText('96%')).toBeInTheDocument();
  expect(screen.getByText('800 GB')).toBeInTheDocument();
  expect(screen.getByText('2 failed')).toBeInTheDocument();
  await userEvent.click(screen.getByText('All time'));
  expect(await screen.findByText('No re-encodes finished in this period yet.')).toBeInTheDocument();
  expect(calls.some((c) => c.key === 'GET stats/performance?days=0')).toBe(true);
});
