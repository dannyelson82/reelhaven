import { MantineProvider } from '@mantine/core';
import { Notifications } from '@mantine/notifications';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';
import { HashRouter } from 'react-router';
import { AuthGate } from './components/AuthGate';
import { theme } from './theme';

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
  });
}

export function App() {
  const [queryClient] = useState(makeQueryClient);
  return (
    // The router wraps everything, so links also work inside notifications and modals.
    <HashRouter>
      <MantineProvider theme={theme} defaultColorScheme="auto">
        <Notifications />
        <QueryClientProvider client={queryClient}>
          <AuthGate />
        </QueryClientProvider>
      </MantineProvider>
    </HashRouter>
  );
}
