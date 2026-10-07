import { MantineProvider } from '@mantine/core';
import { Notifications } from '@mantine/notifications';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { mockApi } from '../test/mockApi';
import { PlanView } from './PlanView';

afterEach(() => vi.unstubAllGlobals());

it('re-encodes a single file without a test run', async () => {
  const calls = mockApi({
    'GET files/7/plan': {
      body: {
        action: 'encode',
        tracks: [],
        flags: [],
        summary: 'Re-encode to HEVC 10-bit.',
        details: [],
        removed_bytes: null,
        video: {
          decision: 'encode',
          reason: 'Estimated saving 40 %.',
          bytes_before: 4e9,
          bytes_after_estimate: 2.4e9,
          savings_percent: 40,
        },
      },
    },
    'POST files/7/apply': { status: 201, body: {} },
  });
  render(
    <MantineProvider>
      <Notifications />
      <QueryClientProvider client={new QueryClient()}>
        <PlanView fileId={7} />
      </QueryClientProvider>
    </MantineProvider>,
  );
  expect(await screen.findByText('Re-encode')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Apply to this file' }));
  expect(await screen.findByText(/Queued/)).toBeInTheDocument();
  expect(calls.some((c) => c.key === 'POST files/7/apply')).toBe(true);
});
