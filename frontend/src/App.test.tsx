import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from './App';
import { mockApi, state } from './test/mockApi';

afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = '';
});

describe('first run', () => {
  it('shows the setup page when no admin exists', async () => {
    mockApi({ 'GET auth/state': state({ setup_required: true }) });
    render(<App />);
    expect(await screen.findByText('Welcome to ReelHaven')).toBeInTheDocument();
  });

  it('checks the passwords match before sending anything', async () => {
    const calls = mockApi({ 'GET auth/state': state({ setup_required: true }) });
    render(<App />);
    await userEvent.type(await screen.findByLabelText('Password'), 'long enough password');
    await userEvent.type(screen.getByLabelText('Confirm password'), 'something else entirely');
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }));
    expect(await screen.findByText('Passwords do not match')).toBeInTheDocument();
    expect(calls.some((c) => c.key === 'POST setup')).toBe(false);
  });

  it('rejects short passwords', async () => {
    mockApi({ 'GET auth/state': state({ setup_required: true }) });
    render(<App />);
    await userEvent.type(await screen.findByLabelText('Password'), 'short');
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }));
    expect(await screen.findByText('Use at least 10 characters')).toBeInTheDocument();
  });

  it('creates the admin and sends the CSRF token', async () => {
    let created = false;
    const calls = mockApi({
      'GET auth/state': () =>
        created
          ? state({ authenticated: true, username: 'admin', method: 'session' })
          : state({ setup_required: true }),
      'POST setup': () => {
        created = true;
        return { status: 201, body: {} };
      },
    });
    render(<App />);
    await userEvent.type(await screen.findByLabelText('Password'), 'long enough password');
    await userEvent.type(screen.getByLabelText('Confirm password'), 'long enough password');
    await userEvent.click(screen.getByRole('button', { name: 'Create account' }));
    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument();
    const post = calls.find((c) => c.key === 'POST setup');
    expect(new Headers(post?.init?.headers).get('X-CSRF-Token')).toBe('csrf-123');
    expect(JSON.parse(String(post?.init?.body))).toEqual({
      username: 'admin',
      password: 'long enough password',
    });
  });
});

describe('login', () => {
  it('explains wrong credentials', async () => {
    mockApi({
      'GET auth/state': state(),
      'POST auth/login': { status: 401, body: { detail: 'invalid_credentials' } },
    });
    render(<App />);
    await userEvent.type(await screen.findByLabelText('Username'), 'admin');
    await userEvent.type(screen.getByLabelText('Password'), 'wrong password');
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }));
    expect(await screen.findByText('Wrong username or password.')).toBeInTheDocument();
  });

  it('shows how long to wait when throttled', async () => {
    mockApi({
      'GET auth/state': state(),
      'POST auth/login': {
        status: 429,
        body: { detail: 'too_many_attempts' },
        headers: { 'Retry-After': '8' },
      },
    });
    render(<App />);
    await userEvent.type(await screen.findByLabelText('Username'), 'admin');
    await userEvent.type(screen.getByLabelText('Password'), 'whatever');
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }));
    expect(await screen.findByText(/Try again in 8 seconds/)).toBeInTheDocument();
  });
});

describe('app', () => {
  it('shows the dashboard and user menu when logged in', async () => {
    mockApi({
      'GET auth/state': state({ authenticated: true, username: 'admin', method: 'session' }),
    });
    render(<App />);
    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument();
    expect(screen.getByText('admin')).toBeInTheDocument();
  });

  it('marks local-network access in the header', async () => {
    mockApi({
      'GET auth/state': state({ authenticated: true, username: 'admin', method: 'bypass' }),
    });
    render(<App />);
    expect(await screen.findByText('(local network)')).toBeInTheDocument();
  });

  it('shows the gateway warning on the security page', async () => {
    window.location.hash = '#/settings/security';
    mockApi({
      'GET auth/state': state({ authenticated: true, username: 'admin', method: 'session' }),
      'GET settings/security': {
        body: {
          local_bypass: true,
          trusted_proxies: [],
          session_idle_days: 7,
          api_key: null,
          client_ip: '192.168.1.20',
          bypass_applies_to_you: true,
          gateway_warning: true,
        },
      },
    });
    render(<App />);
    expect(await screen.findByText("Some requests can't be checked")).toBeInTheDocument();
    expect(screen.getByText('192.168.1.20')).toBeInTheDocument();
  });

  it('reports when the server is unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('network')));
    render(<App />);
    expect(
      await screen.findByText('ReelHaven is not responding', {}, { timeout: 5000 }),
    ).toBeInTheDocument();
  });
});
