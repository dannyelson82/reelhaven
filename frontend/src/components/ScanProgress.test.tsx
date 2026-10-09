import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import type { ScanStatus } from '../api/files';
import { ScanProgress } from './ScanProgress';

const base: ScanStatus = {
  state: 'scanning',
  phase: 'listing',
  found: 0,
  to_match: 0,
  matched: 0,
  to_probe: 0,
  probed: 0,
  failed: 0,
  unchanged: 0,
  moved: 0,
  removed: 0,
  unstable: 0,
  languages_resolved: 0,
  languages_unknown: 0,
  language_errors: [],
  folders: [],
  error: null,
  started_at: 0,
  phase_started_at: 0,
  finished_at: null,
  eta_seconds: null,
};

const show = (status: Partial<ScanStatus>) =>
  render(
    <MantineProvider>
      <ScanProgress status={{ ...base, ...status }} />
    </MantineProvider>,
  );

it('counts files while listing', () => {
  show({ found: 12400 });
  expect(screen.getByText('Looking for video files… 12,400 found so far')).toBeInTheDocument();
  expect(screen.queryByText(/left$/)).not.toBeInTheDocument();
});

it('shows reading progress and the time left', () => {
  show({ phase: 'probing', found: 31000, to_probe: 31000, probed: 3100, eta_seconds: 1500 });
  expect(screen.getByText('Reading files: 3,100 of 31,000')).toBeInTheDocument();
  expect(screen.getByText('about 25 min left')).toBeInTheDocument();
  expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '10');
});

it('shows the check for moved files', () => {
  show({ phase: 'matching', to_match: 40, matched: 10 });
  expect(screen.getByText('Checking for moved or renamed files: 10 of 40')).toBeInTheDocument();
});

it('names the folders of a partial scan', () => {
  show({ phase: 'probing', to_probe: 3, probed: 1, folders: ['Show A', 'Show B', 'C', 'D', 'E'] });
  expect(screen.getByText(/Only what changed: Show A, Show B, C/)).toHaveTextContent(
    'Only what changed: Show A, Show B, C and 2 more',
  );
});
