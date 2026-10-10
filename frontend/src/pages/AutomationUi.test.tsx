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
  last_scan_at: null,
  last_scan_error: null,
  scanning: false,
  watch_mode: 'off',
};
const automation = { paused: false, rescan_enabled: true, rescan_at: '03:00' };

afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = '';
});

it('switches a library to Automatic after confirming', async () => {
  window.location.hash = '#/libraries/1';
  const calls = mockApi({
    'GET auth/state': loggedIn,
    'GET libraries': { body: [library] },
    'GET libraries/1/scan': { body: null },
    'GET libraries/1/files?q=&problems=false&offset=0&limit=50': { body: { total: 0, items: [] } },
    'GET libraries/1/profile': { body: { profile_id: null } },
    'GET profiles': { body: [] },
    'PATCH libraries/1': { body: { ...library, watch_mode: 'automatic' } },
  });
  render(<App />);
  await userEvent.click(await screen.findByRole('combobox', { name: 'Watch mode' }));
  await userEvent.click(
    await screen.findByRole('option', { name: 'Watch mode: Automatic', hidden: true }),
  );
  expect(await screen.findByText(/work through/)).toBeInTheDocument();
  expect(calls.some((c) => c.key === 'PATCH libraries/1')).toBe(false); // not before confirming
  await userEvent.click(screen.getByRole('button', { name: 'Switch to Automatic' }));
  expect(await screen.findByText('Movies: Automatic.')).toBeInTheDocument();
  const patch = calls.find((c) => c.key === 'PATCH libraries/1');
  expect(JSON.parse(String(patch?.init?.body))).toEqual({ watch_mode: 'automatic' });
});

it('pauses and resumes all processing', async () => {
  window.location.hash = '#/jobs';
  let current = automation;
  const calls = mockApi({
    'GET auth/state': loggedIn,
    'GET jobs?status=all&offset=0&limit=50': { body: { total: 0, counts: {}, items: [] } },
    'GET automation': () => ({ body: current }),
    'PUT automation': (init) => {
      current = JSON.parse(String(init?.body));
      return { body: current };
    },
  });
  render(<App />);
  await userEvent.click(await screen.findByRole('button', { name: 'Pause all processing' }));
  expect(await screen.findByText('Processing is paused')).toBeInTheDocument();
  expect(JSON.parse(String(calls.find((c) => c.key === 'PUT automation')?.init?.body))).toEqual({
    ...automation,
    paused: true,
  });
  await userEvent.click(screen.getByRole('button', { name: 'Resume processing' }));
  expect(await screen.findByRole('button', { name: 'Pause all processing' })).toBeInTheDocument();
  expect(screen.queryByText('Processing is paused')).not.toBeInTheDocument();
});

it('says when re-encoding waits for a test run', async () => {
  const waiting = { ...library, watch_mode: 'automatic', needs_test_run: true };
  const api = {
    'GET auth/state': loggedIn,
    'GET libraries': { body: [waiting] },
    'GET libraries/1/scan': { body: null },
    'GET libraries/1/files?q=&problems=false&offset=0&limit=50': { body: { total: 0, items: [] } },
    'GET libraries/1/profile': { body: { profile_id: null } },
    'GET profiles': { body: [] },
  };
  window.location.hash = '#/libraries';
  mockApi(api);
  const { unmount } = render(<App />);
  expect(await screen.findByText('Re-encoding waits for a test run')).toBeInTheDocument();
  unmount();

  window.location.hash = '#/libraries/1';
  mockApi(api);
  render(<App />);
  expect(await screen.findByText('Re-encoding is waiting for a test run')).toBeInTheDocument();
});

it('pauses from the Dashboard too', async () => {
  window.location.hash = '#/';
  let current = automation;
  mockApi({
    'GET auth/state': loggedIn,
    'GET libraries': { body: [{ id: 1, name: 'Movies' }] },
    'GET onboarding': { body: { wizard_seen: true, server_steps_done: true } },
    'GET automation': () => ({ body: current }),
    'PUT automation': (init) => {
      current = JSON.parse(String(init?.body));
      return { body: current };
    },
  });
  render(<App />);
  await userEvent.click(await screen.findByRole('button', { name: 'Pause all processing' }));
  expect(await screen.findByText('Processing is paused')).toBeInTheDocument();
});
