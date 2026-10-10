import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from '../App';
import { mockApi, state } from '../test/mockApi';

const loggedIn = state({ authenticated: true, username: 'admin', method: 'session' });

it('asks before turning the recycle bin off, and keeps longer times without asking', async () => {
  window.location.hash = '#/recycle';
  const calls = mockApi({
    'GET auth/state': loggedIn,
    'GET recycle?show=active': { body: [] },
    'GET settings/recycle': { body: { keep_days: 14 } },
    'PUT settings/recycle': (init) => ({ body: JSON.parse(String(init?.body)) }),
  });
  render(<App />);
  await userEvent.click(await screen.findByText('Off'));
  expect(await screen.findByText('Turn the recycle bin off?')).toBeInTheDocument();
  expect(calls.some((c) => c.key === 'PUT settings/recycle')).toBe(false);
  await userEvent.click(screen.getByRole('button', { name: 'Turn off' }));
  const saved = calls.filter((c) => c.key === 'PUT settings/recycle');
  expect(JSON.parse(String(saved[0]?.init?.body))).toEqual({ keep_days: 0 });
  expect(await screen.findByText('No undo')).toBeInTheDocument();

  // Keeping originals longer again needs no confirmation.
  await userEvent.click(screen.getByText('30 days'));
  expect(calls.filter((c) => c.key === 'PUT settings/recycle')).toHaveLength(2);
});

it('keeps quarantined files on their own tab', async () => {
  window.location.hash = '#/recycle';
  const item = (id: number, reason: string, path: string) => ({
    id,
    library_id: 1,
    original_path: path,
    size: 1e9,
    reason,
    job_id: 5,
    created_at: '2026-10-09T10:00:00Z',
    expires_at: '2026-10-23T10:00:00Z',
    restored_at: null,
    purged_at: null,
  });
  mockApi({
    'GET auth/state': loggedIn,
    'GET recycle?show=active': {
      body: [
        item(1, 'replaced', '/media/Movies/A/a.mkv'),
        item(2, 'quarantine', '/media/TV/Show/S01E01.mkv'),
        item(3, 'wrong-language', '/media/TV/Show/S01E02.mkv'),
      ],
    },
    'GET settings/recycle': { body: { keep_days: 14 } },
  });
  render(<App />);
  expect(await screen.findByText('/media/Movies/A/a.mkv')).toBeInTheDocument();
  expect(screen.getByText(/wrong language, deleted/)).toBeInTheDocument();
  expect(screen.queryByText('/media/TV/Show/S01E01.mkv')).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('tab', { name: /Quarantine/ }));
  expect(await screen.findByText('/media/TV/Show/S01E01.mkv')).toBeInTheDocument();
  expect(screen.getByText(/wrong language, quarantined/)).toBeInTheDocument();
  expect(screen.queryByText('/media/Movies/A/a.mkv')).not.toBeInTheDocument();
});
