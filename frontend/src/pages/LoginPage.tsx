import { Alert, Button, PasswordInput, Stack, TextInput } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useLogin } from '../api/auth';
import { errorMessage } from '../api/client';
import { AuthCard } from '../components/AuthCard';

export function LoginPage() {
  const login = useLogin();
  const form = useForm({
    initialValues: { username: '', password: '' },
    validate: {
      username: (v) => (v.trim() ? null : 'Enter your username'),
      password: (v) => (v ? null : 'Enter your password'),
    },
  });

  return (
    <AuthCard title="Log in to ReelHaven">
      <form
        onSubmit={form.onSubmit(({ username, password }) =>
          login.mutate({ username: username.trim(), password }),
        )}
      >
        <Stack>
          <TextInput
            label="Username"
            autoComplete="username"
            autoFocus
            {...form.getInputProps('username')}
          />
          <PasswordInput
            label="Password"
            autoComplete="current-password"
            {...form.getInputProps('password')}
          />
          {login.isError && <Alert color="red">{errorMessage(login.error)}</Alert>}
          <Button type="submit" loading={login.isPending}>
            Log in
          </Button>
        </Stack>
      </form>
    </AuthCard>
  );
}
