import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from '../App';
import { mockApi, state } from '../test/mockApi';

const loggedIn = state({ authenticated: true, username: 'admin', method: 'session' });

it('turns developer options on, which shows the report downloads', async () => {
  window.location.hash = '#/settings/developer';
  const calls = mockApi({
    'GET auth/state': loggedIn,
    'GET settings/developer': { body: { enabled: false } },
    'PUT settings/developer': (init) => ({ body: JSON.parse(String(init?.body)) }),
  });
  render(<App />);
  const toggle = await screen.findByRole('switch', { name: /Developer options/ });
  expect(screen.queryByText('Download failure report')).not.toBeInTheDocument();
  await userEvent.click(toggle);
  const saved = calls.find((c) => c.key === 'PUT settings/developer');
  expect(JSON.parse(String(saved?.init?.body))).toEqual({ enabled: true });
  expect(await screen.findByRole('link', { name: 'Download failure report' })).toHaveAttribute(
    'href',
    'api/v1/reports/failures',
  );
});
