import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from '../App';
import { mockApi, state } from '../test/mockApi';

const loggedIn = state({ authenticated: true, username: 'admin', method: 'session' });
const saved = {
  id: 3,
  kind: 'sonarr',
  name: 'Sonarr',
  base_url: 'http://10.0.0.5:8989',
  verify_tls: true,
  path_mappings: [{ remote: '/tv', local: '/media/TV' }],
  enabled: true,
  api_key_hint: '…cdef',
};

beforeEach(() => {
  window.location.hash = '#/settings/integrations';
});
afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = '';
});

it('adds Sonarr after a successful connection test', async () => {
  const calls = mockApi({
    'GET auth/state': loggedIn,
    'GET integrations': { body: [] },
    'POST integrations/test': {
      body: { ok: true, app: 'Sonarr', version: '4.0.9', error_code: null, message: null },
    },
    'POST integrations': { status: 201, body: saved },
  });
  render(<App />);
  await userEvent.click(await screen.findByRole('button', { name: 'Add Sonarr' }));
  await userEvent.type(await screen.findByLabelText('Address'), 'http://10.0.0.5:8989');
  await userEvent.type(screen.getByLabelText('API key'), '0123456789abcdef');
  await userEvent.click(screen.getByRole('button', { name: 'Test connection' }));
  expect(await screen.findByText('Connected to Sonarr 4.0.9')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Save' }));
  expect(await screen.findByText('Sonarr saved.')).toBeInTheDocument();
  const post = calls.find((c) => c.key === 'POST integrations');
  expect(JSON.parse(String(post?.init?.body))).toMatchObject({
    kind: 'sonarr',
    base_url: 'http://10.0.0.5:8989',
    api_key: '0123456789abcdef',
  });
});

it('shows why a connection test failed', async () => {
  mockApi({
    'GET auth/state': loggedIn,
    'GET integrations': { body: [] },
    'POST integrations/test': {
      body: {
        ok: false,
        app: null,
        version: null,
        error_code: 'unauthorized',
        message: 'The API key was rejected',
      },
    },
  });
  render(<App />);
  await userEvent.click(await screen.findByRole('button', { name: 'Add Radarr' }));
  await userEvent.type(await screen.findByLabelText('Address'), 'http://10.0.0.5:7878');
  await userEvent.type(screen.getByLabelText('API key'), 'wrong');
  await userEvent.click(screen.getByRole('button', { name: 'Test connection' }));
  expect(await screen.findByText('The API key was rejected')).toBeInTheDocument();
});

it('keeps the saved key when the key field is left empty', async () => {
  const calls = mockApi({
    'GET auth/state': loggedIn,
    'GET integrations': { body: [saved] },
    'PATCH integrations/3': { body: { ...saved, name: 'Sonarr HD' } },
  });
  render(<App />);
  await userEvent.click(await screen.findByRole('button', { name: 'Edit' }));
  const name = await screen.findByLabelText('Name');
  await userEvent.clear(name);
  await userEvent.type(name, 'Sonarr HD');
  await userEvent.click(screen.getByRole('button', { name: 'Save' }));
  await screen.findByText('Sonarr HD saved.');
  const patch = calls.find((c) => c.key === 'PATCH integrations/3');
  const body = JSON.parse(String(patch?.init?.body));
  expect(body).not.toHaveProperty('api_key');
  expect(body).not.toHaveProperty('kind');
  expect(body.name).toBe('Sonarr HD');
});

it('shows how to set up webhooks and what arrived last', async () => {
  window.location.hash = '#/settings/integrations';
  mockApi({
    'GET auth/state': state({ authenticated: true, username: 'admin', method: 'session' }),
    'GET integrations': { body: [] },
    'GET webhooks': {
      body: {
        sonarr: {
          at: '2026-10-07T20:00:00Z',
          event: 'Test',
          outcome: 'test',
          message: 'Sonarr can reach ReelHaven.',
          library: null,
          path: null,
        },
        radarr: null,
      },
    },
  });
  render(<App />);
  expect(await screen.findByText('Webhooks')).toBeInTheDocument();
  expect(screen.getByText(/api\/v1\/webhook\/sonarr\?apikey=YOUR_API_KEY/)).toBeInTheDocument();
  expect(screen.getByText(/api\/v1\/webhook\/radarr\?apikey=YOUR_API_KEY/)).toBeInTheDocument();
  expect(await screen.findByText(/Sonarr can reach ReelHaven\./)).toBeInTheDocument();
  expect(screen.getByText('Nothing received yet.')).toBeInTheDocument();
});

it('adds Plex and shows the last update sent', async () => {
  window.location.hash = '#/settings/integrations';
  mockApi({
    'GET auth/state': state({ authenticated: true, username: 'admin', method: 'session' }),
    'GET integrations': {
      body: [
        {
          id: 9,
          kind: 'plex',
          name: 'Plex',
          base_url: 'http://10.0.0.5:32400',
          verify_tls: true,
          path_mappings: [],
          enabled: true,
          api_key_hint: '…3abc',
          last_notify: {
            at: '2026-10-07T20:00:00Z',
            ok: false,
            message: 'The API key was rejected',
          },
        },
      ],
    },
    'GET webhooks': { body: { sonarr: null, radarr: null } },
  });
  render(<App />);
  expect(await screen.findByText(/Token …3abc/)).toBeInTheDocument();
  expect(screen.getByText(/The API key was rejected/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Add Plex' }));
  expect(await screen.findByLabelText('Plex token')).toBeInTheDocument();
  expect(screen.getByPlaceholderText('http://192.168.1.10:32400')).toBeInTheDocument();
  expect(screen.getByText(/X-Plex-Token/)).toBeInTheDocument();
});
