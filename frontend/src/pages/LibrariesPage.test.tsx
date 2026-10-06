import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from '../App';
import { mockApi, state } from '../test/mockApi';

const loggedIn = state({ authenticated: true, username: 'admin', method: 'session' });

afterEach(() => {
  vi.unstubAllGlobals();
  window.location.hash = '';
});

describe('libraries', () => {
  beforeEach(() => {
    window.location.hash = '#/libraries';
  });

  it('explains what to do when there are no libraries', async () => {
    mockApi({ 'GET auth/state': loggedIn, 'GET libraries': { body: [] } });
    render(<App />);
    expect(await screen.findByText(/No libraries yet/)).toBeInTheDocument();
  });

  it('adds a library by browsing to a folder', async () => {
    const calls = mockApi({
      'GET auth/state': loggedIn,
      'GET libraries': { body: [] },
      'GET browse?path=': {
        body: {
          path: '',
          parent: null,
          truncated: false,
          dirs: [{ name: 'Film Folder', path: 'Film Folder' }],
        },
      },
      'GET browse?path=Film%20Folder': {
        body: { path: 'Film Folder', parent: '', truncated: false, dirs: [] },
      },
      'POST libraries': {
        status: 201,
        body: {
          id: 1,
          name: 'Films',
          type: 'movies',
          path: '/media/Movies',
          relative_path: 'Film Folder',
          created_at: '',
        },
      },
    });
    render(<App />);
    await userEvent.click(await screen.findByRole('button', { name: 'Add library' }));
    await userEvent.type(await screen.findByLabelText('Name'), 'Films');
    fireEvent.click(await screen.findByText('Film Folder'));
    expect(await screen.findByText('/media/Film Folder')).toBeInTheDocument();
    const dialog = screen.getByRole('dialog');
    await userEvent.click(
      Array.from(dialog.querySelectorAll('button')).find((b) => b.textContent === 'Add library')!,
    );
    expect(await screen.findByText('Library "Films" added.')).toBeInTheDocument();
    const post = calls.find((c) => c.key === 'POST libraries');
    expect(JSON.parse(String(post?.init?.body))).toEqual({
      name: 'Films',
      type: 'movies',
      path: 'Film Folder',
    });
  });

  it('requires a folder before adding', async () => {
    const calls = mockApi({
      'GET auth/state': loggedIn,
      'GET libraries': { body: [] },
      'GET browse?path=': { body: { path: '', parent: null, truncated: false, dirs: [] } },
    });
    render(<App />);
    await userEvent.click(await screen.findByRole('button', { name: 'Add library' }));
    await userEvent.type(await screen.findByLabelText('Name'), 'Films');
    const dialog = screen.getByRole('dialog');
    await userEvent.click(
      Array.from(dialog.querySelectorAll('button')).find((b) => b.textContent === 'Add library')!,
    );
    expect(await screen.findByText('Choose a folder')).toBeInTheDocument();
    expect(calls.some((c) => c.key === 'POST libraries')).toBe(false);
  });

  it('shows server errors in plain language', async () => {
    mockApi({
      'GET auth/state': loggedIn,
      'GET libraries': { body: [] },
      'GET browse?path=': {
        body: { path: '', parent: null, truncated: false, dirs: [{ name: 'TV', path: 'TV' }] },
      },
      'GET browse?path=TV': { body: { path: 'TV', parent: '', truncated: false, dirs: [] } },
      'POST libraries': { status: 409, body: { detail: 'path_overlaps_library' } },
    });
    render(<App />);
    await userEvent.click(await screen.findByRole('button', { name: 'Add library' }));
    await userEvent.type(await screen.findByLabelText('Name'), 'Shows');
    fireEvent.click(await screen.findByText('TV'));
    const dialog = screen.getByRole('dialog');
    await userEvent.click(
      Array.from(dialog.querySelectorAll('button')).find((b) => b.textContent === 'Add library')!,
    );
    expect(await screen.findByText(/already part of another library/)).toBeInTheDocument();
  });
});
