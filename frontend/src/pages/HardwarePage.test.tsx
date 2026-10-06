import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from '../App';
import { mockApi, state } from '../test/mockApi';

const loggedIn = state({ authenticated: true, username: 'admin', method: 'session' });
const ok = (codec: string, ten_bit: boolean, encoder: string) => ({
  codec,
  ten_bit,
  encoder,
  ok: true,
  error: null,
  seconds: 0.4,
});
const response = {
  detecting: false,
  detected_at: 1,
  settings: { cpu_enabled: false, cpu_concurrency: 1, devices: {} },
  devices: [
    {
      id: 'nvidia:0',
      kind: 'nvidia',
      name: 'RTX 3060',
      family: 'nvenc',
      enabled: true,
      concurrency: 2,
      results: [
        ok('hevc', false, 'hevc_nvenc'),
        ok('hevc', true, 'hevc_nvenc'),
        {
          codec: 'av1',
          ten_bit: false,
          encoder: 'av1_nvenc',
          ok: false,
          error: 'No capable devices found',
          seconds: 0.2,
        },
      ],
    },
    {
      id: 'cpu',
      kind: 'cpu',
      name: 'CPU (software)',
      family: 'cpu',
      enabled: false,
      concurrency: 1,
      results: [ok('hevc', false, 'libx265')],
    },
  ],
};

afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = '';
});

it('shows what each device can encode and toggles CPU encoding', async () => {
  window.location.hash = '#/settings/hardware';
  const calls = mockApi({
    'GET auth/state': loggedIn,
    'GET devices': { body: response },
    'PUT devices/settings': (init) => ({
      body: { ...response, settings: JSON.parse(String(init?.body)) },
    }),
  });
  render(<App />);
  expect(await screen.findByText('RTX 3060')).toBeInTheDocument();
  expect(screen.getAllByText('hevc_nvenc')).toHaveLength(2);
  expect(screen.getAllByText('not supported').length).toBeGreaterThan(0);
  await userEvent.click(screen.getByLabelText('Allow CPU encoding (slow)'));
  const put = calls.find((c) => c.key === 'PUT devices/settings');
  expect(JSON.parse(String(put?.init?.body))).toMatchObject({ cpu_enabled: true });
});

it('explains how to pass a GPU through when none is found', async () => {
  window.location.hash = '#/settings/hardware';
  mockApi({
    'GET auth/state': loggedIn,
    'GET devices': { body: { ...response, devices: [response.devices[1]] } },
  });
  render(<App />);
  expect(await screen.findByText('No GPU found')).toBeInTheDocument();
});
