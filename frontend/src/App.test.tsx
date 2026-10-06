import { render, screen } from '@testing-library/react';
import { App } from './App';

describe('App', () => {
  it('renders the home page', () => {
    render(<App />);
    expect(screen.getByRole('heading', { name: 'ReelHaven' })).toBeInTheDocument();
  });
});
