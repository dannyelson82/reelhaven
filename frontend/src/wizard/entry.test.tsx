import { render, screen } from '@testing-library/react';
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
    'GET browse?path=': { body: { path: '', parent: null, truncated: false, dirs: [] } },
  });
  render(<App />);
  expect(await screen.findByText('Set up automatic compression')).toBeInTheDocument();
  expect(window.location.hash).toBe('#/wizard');
  expect(await screen.findByText(/Which folder holds the videos/)).toBeInTheDocument();
  await screen.findByText(/Which folder/); // let the onboarding save settle
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
