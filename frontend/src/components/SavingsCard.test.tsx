import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from '../App';
import { mockApi, state } from '../test/mockApi';

const loggedIn = state({ authenticated: true, username: 'admin', method: 'session' });
const weeks = Array.from({ length: 12 }, (_, i) => ({
  start: `2026-${String(7 + Math.floor((i + 20) / 4.4)).padStart(2, '0')}-0${(i % 9) + 1}`,
  saved: i === 11 ? 4e9 : i === 10 ? 2e9 : 0,
  files: i === 11 ? 3 : i === 10 ? 1 : 0,
}));
const months = Array.from({ length: 12 }, (_, i) => ({
  start: `20${i < 2 ? '25' : '26'}-${String(((i + 10) % 12) + 1).padStart(2, '0')}-01`,
  saved: i === 11 ? 6e9 : i === 10 ? 10e9 : 0,
  files: i === 11 ? 4 : i === 10 ? 2 : 0,
}));
const savings = {
  total_saved: 16e9,
  files: 6,
  this_week: 4e9,
  this_month: 6e9,
  weekly: weeks,
  monthly: months,
  libraries: [
    { library_id: 1, name: 'Movies', saved: 12e9, files: 4 },
    { library_id: 2, name: 'TV', saved: 4e9, files: 2 },
  ],
};
const page = {
  'GET auth/state': loggedIn,
  'GET libraries': { body: [{ id: 1, name: 'Movies' }] },
  'GET onboarding': { body: { wizard_seen: true, server_steps_done: true } },
  'GET jobs?status=active&offset=0&limit=50': { body: { total: 0, counts: {}, items: [] } },
};

afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = '';
});

it('shows the space saved with a table view', async () => {
  window.location.hash = '#/';
  mockApi({ ...page, 'GET stats/savings': { body: savings } });
  render(<App />);
  expect(await screen.findByText('Space saved')).toBeInTheDocument();
  expect(screen.getByText('16.0 GB')).toBeInTheDocument(); // since install
  expect(screen.getByText('4.0 GB')).toBeInTheDocument(); // this week
  expect(screen.getByText('6.0 GB')).toBeInTheDocument(); // this month
  expect(screen.getByText('6')).toBeInTheDocument(); // files
  expect(screen.getByText('12.0 GB · 4 files')).toBeInTheDocument(); // by library

  await userEvent.click(screen.getByRole('button', { name: 'Show as table' }));
  expect(screen.getByRole('columnheader', { name: 'Week of' })).toBeInTheDocument();
  expect(screen.getAllByRole('row')).toHaveLength(13); // header + 12 weeks
  await userEvent.click(screen.getByText('Monthly'));
  expect(screen.getByRole('columnheader', { name: 'Month' })).toBeInTheDocument();
  expect(screen.getByText('10.0 GB')).toBeInTheDocument();
});

it('stays out of the way until something was saved', async () => {
  window.location.hash = '#/';
  mockApi({
    ...page,
    'GET stats/savings': {
      body: { ...savings, total_saved: 0, files: 0, this_week: 0, this_month: 0, libraries: [] },
    },
  });
  render(<App />);
  expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument();
  expect(screen.queryByText('Space saved')).not.toBeInTheDocument();
});
