import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from '../App';
import { mockApi, state } from '../test/mockApi';

const loggedIn = state({ authenticated: true, username: 'admin', method: 'session' });

afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = '';
});

it('opens the wizard on the first visit', async () => {
  window.location.hash = '#/';
  const calls = mockApi({
    'GET auth/state': loggedIn,
    'GET libraries': { body: [] },
    'GET onboarding': { body: { wizard_seen: false, server_steps_done: false } },
    'PUT onboarding': (init) => ({ body: JSON.parse(String(init?.body)) }),
    'GET jobs?status=active&offset=0&limit=50': { body: { total: 0, counts: {}, items: [] } },
    'GET devices': { body: { devices: [], settings: {}, detected_at: null, detecting: true } },
  });
  render(<App />);
  expect(await screen.findByText('Set up automatic compression')).toBeInTheDocument();
  expect(window.location.hash).toBe('#/wizard');
  // A new server starts with the hardware step.
  expect(await screen.findByText(/Trying a short test encode/)).toBeInTheDocument();
  expect(calls.some((c) => c.key === 'PUT onboarding')).toBe(true);
});

it('offers the wizard on the dashboard once it has been seen', async () => {
  window.location.hash = '#/';
  mockApi({
    'GET auth/state': loggedIn,
    'GET libraries': { body: [] },
    'GET onboarding': { body: { wizard_seen: true, server_steps_done: false } },
    'GET jobs?status=active&offset=0&limit=50': { body: { total: 0, counts: {}, items: [] } },
  });
  render(<App />);
  expect(await screen.findByText('Welcome to ReelHaven')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /Set up your first library/ })).toHaveAttribute(
    'href',
    '#/wizard',
  );
});

it('asks about hardware and apps once per server', async () => {
  window.location.hash = '#/wizard';
  const settings = { cpu_enabled: false, cpu_concurrency: 1, devices: {} };
  let onboarding = { wizard_seen: true, server_steps_done: false };
  const calls = mockApi({
    'GET auth/state': loggedIn,
    'GET onboarding': () => ({ body: onboarding }),
    'PUT onboarding': (init) => {
      onboarding = JSON.parse(String(init?.body));
      return { body: onboarding };
    },
    'GET devices': {
      body: {
        detecting: false,
        detected_at: 1,
        settings,
        devices: [
          {
            id: 'cpu',
            kind: 'cpu',
            name: 'CPU (software)',
            family: 'cpu',
            enabled: false,
            concurrency: 1,
            results: [
              {
                codec: 'hevc',
                ten_bit: true,
                encoder: 'libx265',
                ok: true,
                error: null,
                seconds: 1,
              },
            ],
          },
        ],
      },
    },
    'PUT devices/settings': (init) => ({
      body: {
        detecting: false,
        detected_at: 1,
        settings: JSON.parse(String(init?.body)),
        devices: [],
      },
    }),
    'GET integrations': { body: [] },
    'GET browse?path=': { body: { path: '', parent: null, truncated: false, dirs: [] } },
  });
  render(<App />);

  // Hardware: no GPU, so the processor can be allowed instead.
  expect(await screen.findByText('No graphics card found')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('switch', { name: /Allow CPU encoding/ }));
  const put = calls.find((c) => c.key === 'PUT devices/settings');
  expect(JSON.parse(String(put?.init?.body))).toEqual({ ...settings, cpu_enabled: true });
  await userEvent.click(screen.getByRole('button', { name: 'Next' }));

  // Apps: optional; Add opens the usual form.
  expect(await screen.findByText(/Do you use any of these/)).toBeInTheDocument();
  await userEvent.click(screen.getAllByRole('button', { name: 'Add' })[2]); // Plex
  expect(await screen.findByLabelText('Plex token')).toBeInTheDocument();
  await userEvent.keyboard('{Escape}');
  await userEvent.click(screen.getByRole('button', { name: 'Skip' }));

  // Remembered: the library steps follow, and the server steps won't be asked again.
  expect(await screen.findByText(/Which folder holds the videos/)).toBeInTheDocument();
  expect(onboarding.server_steps_done).toBe(true);
  expect(screen.queryByText('Your apps')).not.toBeInTheDocument(); // gone from the stepper
});
