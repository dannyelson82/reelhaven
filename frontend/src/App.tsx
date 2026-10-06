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
    <MantineProvider theme={theme} defaultColorScheme="auto">
      <Notifications />
      <QueryClientProvider client={queryClient}>
        <HashRouter>
          <AuthGate />
        </HashRouter>
      </QueryClientProvider>
    </MantineProvider>
  );
}
