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
