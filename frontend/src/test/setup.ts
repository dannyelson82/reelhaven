import '@testing-library/jest-dom/vitest';
import { configure } from '@testing-library/react';
import { FakeSocket } from './fakeSocket';

// CI machines are slower than a dev box and Mantine animates menus and modals;
// the 1 s default made tests fail there at random.
configure({ asyncUtilTimeout: 3000 });

// Mantine reads these browser APIs, which jsdom doesn't implement.
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }),
});

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
window.ResizeObserver = ResizeObserverStub;

// Mantine's autosize Textarea listens for web fonts loading.
if (!('fonts' in document)) {
  Object.defineProperty(document, 'fonts', {
    value: { addEventListener: () => {}, removeEventListener: () => {}, ready: Promise.resolve() },
  });
}

// Live job updates: a fake socket instead of a real connection.
window.WebSocket = FakeSocket as unknown as typeof WebSocket;
afterEach(() => {
  FakeSocket.instances = [];
});
