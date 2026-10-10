import {
  AppShell,
  Badge,
  Burger,
  Group,
  Image,
  Menu,
  NavLink,
  Text,
  UnstyledButton,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import {
  IconChevronDown,
  IconCpu2,
  IconListCheck,
  IconMovie,
  IconRecycle,
  IconFolders,
  IconAlertTriangle,
  IconGauge,
  IconLogout,
  IconPlugConnected,
  IconShieldLock,
} from '@tabler/icons-react';
import { NavLink as RouterLink, Outlet, useLocation } from 'react-router';
import { type AuthState, useLogout, useLogoutEverywhere } from '../api/auth';
import { useLiveConnection, useLiveJobs } from '../api/live';
import { useReviewCount } from '../api/review';

const NAV = [
  { to: '/', label: 'Dashboard', icon: IconGauge },
  { to: '/libraries', label: 'Libraries', icon: IconFolders },
  { to: '/profiles', label: 'Profiles', icon: IconMovie },
  { to: '/jobs', label: 'Jobs', icon: IconListCheck },
  { to: '/review', label: 'Review', icon: IconAlertTriangle },
  { to: '/recycle', label: 'Recycle bin', icon: IconRecycle },
  { to: '/settings/hardware', label: 'Hardware', icon: IconCpu2 },
  { to: '/settings/integrations', label: 'Integrations', icon: IconPlugConnected },
  { to: '/settings/security', label: 'Security', icon: IconShieldLock },
];

export function AppLayout({ auth }: { auth: AuthState }) {
  const [opened, { toggle, close }] = useDisclosure();
  const location = useLocation();
  const logout = useLogout();
  const logoutEverywhere = useLogoutEverywhere();
  // SECURITY.md: the socket needs a real session; the local-network bypass polls instead.
  useLiveConnection(auth.method === 'session');
  const live = useLiveJobs();
  const busy = live ? (live.counts.queued ?? 0) + live.active.length : 0;
  const toReview = useReviewCount();

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
            rightSection={
              to === '/jobs' && busy > 0 ? (
                <Badge size="sm" variant="light" aria-label={`${busy} jobs in progress`}>
                  {busy}
                </Badge>
              ) : to === '/review' && toReview > 0 ? (
                <Badge
                  size="sm"
                  variant="light"
                  color="orange"
                  aria-label={`${toReview} files to review`}
                >
                  {toReview}
                </Badge>
              ) : undefined
            }
            active={to === '/' ? location.pathname === '/' : location.pathname.startsWith(to)}
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
