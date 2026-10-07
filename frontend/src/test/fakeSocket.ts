// A stand-in for the browser WebSocket: tests push server messages with
// `push()`. Installed for every test in setup.ts, so nothing touches the network.

export class FakeSocket {
  static instances: FakeSocket[] = [];
  readonly url: string;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onclose: (() => void) | null = null;
  closed = false;

  constructor(url: string) {
    this.url = url;
    FakeSocket.instances.push(this);
  }

  close() {
    if (this.closed) return;
    this.closed = true;
    this.onclose?.();
  }
}

/** Send a server message to every open socket. */
export function push(message: unknown) {
  for (const socket of FakeSocket.instances) {
    if (!socket.closed) {
      socket.onmessage?.(new MessageEvent('message', { data: JSON.stringify(message) }));
    }
  }
}
