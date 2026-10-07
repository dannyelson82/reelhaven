// Live job progress over a WebSocket (ARCHITECTURE.md §11.1).
//
// The server pushes the running jobs and the queue counts whenever something
// changes. Pages read them with useLiveJobs(); while the socket is down they
// fall back to polling, so nothing depends on it.

import { type QueryClient, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import type { Job } from './jobs';

export interface LiveJobs {
  counts: Record<string, number>;
  active: Job[];
}

const LIVE_KEY = ['live-jobs'];
const MAX_RETRY_MS = 60_000;

/** The latest pushed snapshot, or null while not connected. */
export function useLiveJobs(): LiveJobs | null {
  return (
    useQuery({ queryKey: LIVE_KEY, queryFn: () => null as LiveJobs | null, enabled: false }).data ??
    null
  );
}

/** For refetchInterval callbacks: is the socket feeding fresh data? */
export const liveConnected = (queryClient: QueryClient) =>
  queryClient.getQueryData<LiveJobs | null>(LIVE_KEY) != null;

/** The pushed version of a job (fresher progress) if it is running, else the job itself. */
export function withLive(job: Job, live: LiveJobs | null): Job {
  return live?.active.find((j) => j.id === job.id) ?? job;
}

function socketUrl(): string {
  const url = new URL('api/v1/ws', document.baseURI);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return url.toString();
}

const shape = (live: LiveJobs) =>
  JSON.stringify([live.counts, live.active.map((j) => [j.id, j.status])]);

/** Keep one socket open while `enabled`, reconnecting with a growing delay. */
export function useLiveConnection(enabled: boolean) {
  const queryClient = useQueryClient();
  useEffect(() => {
    if (!enabled) return;
    let socket: WebSocket | null = null;
    let retryMs = 1000;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;
    let previous: LiveJobs | null = null;

    const refresh = (live: LiveJobs) => {
      if (previous === null || shape(previous) === shape(live)) return;
      // A job started, finished or was queued: lists and test runs are out of date.
      void queryClient.invalidateQueries({ queryKey: ['jobs'] });
      void queryClient.invalidateQueries({ queryKey: ['test-run'] });
      const ended = (c: Record<string, number>) =>
        (c.done ?? 0) + (c.failed ?? 0) + (c.cancelled ?? 0);
      if (ended(live.counts) > ended(previous.counts)) {
        for (const key of ['files', 'plan', 'recycle']) {
          void queryClient.invalidateQueries({ queryKey: [key] });
        }
      }
    };

    const connect = () => {
      socket = new WebSocket(socketUrl());
      socket.onmessage = (event: MessageEvent<string>) => {
        const live = JSON.parse(event.data) as LiveJobs & { type: string };
        if (live.type !== 'jobs') return;
        retryMs = 1000;
        refresh(live);
        previous = live;
        queryClient.setQueryData(LIVE_KEY, { counts: live.counts, active: live.active });
      };
      socket.onclose = () => {
        queryClient.setQueryData(LIVE_KEY, null);
        previous = null;
        if (stopped) return;
        timer = setTimeout(connect, retryMs);
        retryMs = Math.min(retryMs * 2, MAX_RETRY_MS);
      };
    };
    connect();
    return () => {
      stopped = true;
      clearTimeout(timer);
      socket?.close();
      queryClient.setQueryData(LIVE_KEY, null);
    };
  }, [enabled, queryClient]);
}
