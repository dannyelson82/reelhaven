import { Alert, Center, Loader } from '@mantine/core';
import { Route, Routes } from 'react-router';
import { useAuthState } from '../api/auth';
import { errorMessage } from '../api/client';
import { DashboardPage } from '../pages/DashboardPage';
import { LibrariesPage } from '../pages/LibrariesPage';
import { LibraryPage } from '../pages/LibraryPage';
import { LoginPage } from '../pages/LoginPage';
import { SecurityPage } from '../pages/SecurityPage';
import { SetupPage } from '../pages/SetupPage';
import { AppLayout } from './AppLayout';

/** Shows setup, login or the app depending on the server's auth state. */
export function AuthGate() {
  const auth = useAuthState();

  if (auth.isPending) {
    return (
      <Center mih="100vh">
        <Loader />
      </Center>
    );
  }
  if (auth.isError) {
    return (
      <Center mih="100vh" p="md">
        <Alert color="red" title="ReelHaven is not responding">
          {errorMessage(auth.error)}
        </Alert>
      </Center>
    );
  }
  if (auth.data.setup_required) return <SetupPage />;
  if (!auth.data.authenticated) return <LoginPage />;

  return (
    <Routes>
      <Route element={<AppLayout auth={auth.data} />}>
        <Route index element={<DashboardPage />} />
        <Route path="libraries" element={<LibrariesPage />} />
        <Route path="libraries/:id" element={<LibraryPage />} />
        <Route path="settings/security" element={<SecurityPage />} />
        <Route path="*" element={<DashboardPage />} />
      </Route>
    </Routes>
  );
}
