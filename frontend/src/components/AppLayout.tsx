import { AppShell, Burger, Group, Image, Menu, NavLink, Text, UnstyledButton } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { IconChevronDown, IconGauge, IconLogout, IconShieldLock } from '@tabler/icons-react';
import { NavLink as RouterLink, Outlet, useLocation } from 'react-router';
import { type AuthState, useLogout, useLogoutEverywhere } from '../api/auth';

const NAV = [
  { to: '/', label: 'Dashboard', icon: IconGauge },
  { to: '/settings/security', label: 'Security', icon: IconShieldLock },
];

export function AppLayout({ auth }: { auth: AuthState }) {
  const [opened, { toggle, close }] = useDisclosure();
  const location = useLocation();
  const logout = useLogout();
  const logoutEverywhere = useLogoutEverywhere();

  return (
    <AppShell
      header={{ height: 56 }}
      navbar={{ width: 220, breakpoint: 'sm', collapsed: { mobile: !opened } }}
      padding="md"
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group gap="xs">
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" />
            <Image src="./favicon.svg" w={28} h={28} alt="" />
            <Text fw={700}>ReelHaven</Text>
          </Group>
          <Menu position="bottom-end">
            <Menu.Target>
              <UnstyledButton>
                <Group gap={4}>
                  <Text size="sm">{auth.username}</Text>
                  {auth.method === 'bypass' && (
                    <Text size="xs" c="dimmed">
                      (local network)
                    </Text>
                  )}
                  <IconChevronDown size={14} />
                </Group>
              </UnstyledButton>
            </Menu.Target>
            <Menu.Dropdown>
              {auth.method === 'session' && (
                <Menu.Item leftSection={<IconLogout size={14} />} onClick={() => logout.mutate()}>
                  Log out
                </Menu.Item>
              )}
              <Menu.Item color="red" onClick={() => logoutEverywhere.mutate()}>
                Log out everywhere
              </Menu.Item>
            </Menu.Dropdown>
          </Menu>
        </Group>
      </AppShell.Header>
      <AppShell.Navbar p="xs">
        {NAV.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            component={RouterLink}
            to={to}
            label={label}
            leftSection={<Icon size={18} />}
            active={location.pathname === to}
            onClick={close}
          />
        ))}
      </AppShell.Navbar>
      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}
