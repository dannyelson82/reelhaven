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
