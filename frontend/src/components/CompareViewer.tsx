import {
  ActionIcon,
  Box,
  Button,
  Group,
  Loader,
  Modal,
  SegmentedControl,
  Slider,
  Stack,
  Text,
  Tooltip,
} from '@mantine/core';
import { useMediaQuery } from '@mantine/hooks';
import { IconZoomIn, IconZoomOut } from '@tabler/icons-react';
import { type PointerEvent, useEffect, useRef, useState } from 'react';
import { formatDuration } from '../format';
import {
  FIT,
  MAX_ZOOM,
  type Size,
  type View,
  actualPixels,
  clamp,
  pan,
  placement,
  zoomTo,
} from './compareView';

export interface Still {
  /** Seconds into the video. */
  at: number;
  source: string;
  encoded: string;
}

type Mode = 'side' | 'swipe';

const STEP = 1.25;
const NO_SIZE: Size = { width: 16, height: 9 };

/** Full-screen comparison of original and re-encoded stills: side by side with one zoom
 * and synced panning, or one image with a draggable divider. Render it only while open, so
 * it starts at `start` each time. */
export function CompareViewer({
  opened,
  onClose,
  title,
  stills,
  start = 0,
  after = 'Re-encoded',
  note,
}: {
  opened: boolean;
  onClose: () => void;
  title: string;
  stills: Still[];
  start?: number;
  /** What the new version is called ("Re-encoded", "Smaller"). */
  after?: string;
  note?: string;
}) {
  const [index, setIndex] = useState(start);
  const [mode, setMode] = useState<Mode>('side');
  const [view, setView] = useState<View>(FIT);
  const [divider, setDivider] = useState(0.5);
  const [image, setImage] = useState<Size | null>(null);
  const [loaded, setLoaded] = useState<Set<string>>(new Set());
  const [pane, setPane] = useState<Size>(NO_SIZE);
  const paneRef = useRef<HTMLDivElement | null>(null);
  const narrow = useMediaQuery('(max-width: 48em)');

  // Both panes are the same size; measure the first.
  useEffect(() => {
    const element = paneRef.current;
    if (!element) return;
    const measure = () =>
      setPane({ width: element.clientWidth || 1, height: element.clientHeight || 1 });
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [opened, mode, narrow]);

  const size = image ?? NO_SIZE;
  const still = stills[Math.min(index, stills.length - 1)];
  const ready = still !== undefined && loaded.has(still.source) && loaded.has(still.encoded);

  const zoomBy = (factor: number) => setView((v) => zoomTo(v, v.zoom * factor, pane, size));
  const setZoom = (zoom: number) => setView((v) => zoomTo(v, zoom, pane, size));
  const actual = actualPixels(pane, size);

  useEffect(() => {
    if (!opened) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement) return;
      const keys: Record<string, () => void> = {
        ArrowLeft: () => setIndex((i) => Math.max(0, i - 1)),
        ArrowRight: () => setIndex((i) => Math.min(stills.length - 1, i + 1)),
        '+': () => zoomBy(STEP),
        '=': () => zoomBy(STEP),
        '-': () => zoomBy(1 / STEP),
        '0': () => setView(FIT),
        '1': () => setZoom(actual),
        s: () => setMode((m) => (m === 'side' ? 'swipe' : 'side')),
      };
      const action = keys[event.key];
      if (action) {
        event.preventDefault();
        action();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  // Dragging pans (one finger or the mouse); two fingers pinch to zoom.
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    pointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
  };
  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const last = pointers.current.get(event.pointerId);
    if (!last) return;
    const now = { x: event.clientX, y: event.clientY };
    const others = [...pointers.current.entries()].filter(([id]) => id !== event.pointerId);
    if (others.length === 1) {
      const other = others[0][1];
      const before = Math.hypot(last.x - other.x, last.y - other.y);
      const after = Math.hypot(now.x - other.x, now.y - other.y);
      const box = event.currentTarget.getBoundingClientRect();
      const x = (now.x + other.x) / 2 - box.left;
      const y = (now.y + other.y) / 2 - box.top;
      if (before > 0) setView((v) => zoomTo(v, (v.zoom * after) / before, pane, size, x, y));
    } else {
      setView((v) => pan(v, now.x - last.x, now.y - last.y, pane, size));
    }
    pointers.current.set(event.pointerId, now);
  };
  const onPointerUp = (event: PointerEvent<HTMLDivElement>) => {
    pointers.current.delete(event.pointerId);
  };

  // The wheel zooms around the pointer; React's wheel listener can't stop the page scrolling.
  const wheelTarget = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    const element = wheelTarget.current;
    if (!element) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const target = (event.target as HTMLElement).closest('[data-pane]') ?? element;
      const box = target.getBoundingClientRect();
      const factor = event.deltaY < 0 ? STEP : 1 / STEP;
      setView((v) =>
        zoomTo(v, v.zoom * factor, pane, size, event.clientX - box.left, event.clientY - box.top),
      );
    };
    element.addEventListener('wheel', onWheel, { passive: false });
    return () => element.removeEventListener('wheel', onWheel);
  });

  const onLoad = (src: string) => (event: React.SyntheticEvent<HTMLImageElement>) => {
    const img = event.currentTarget;
    if (img.naturalWidth > 0) {
      setImage((current) => current ?? { width: img.naturalWidth, height: img.naturalHeight });
    }
    setLoaded((current) => new Set(current).add(src));
  };

  const at = placement(clamp(view, pane, size), pane, size);
  const imageStyle = {
    position: 'absolute' as const,
    left: at.left,
    top: at.top,
    width: at.width,
    height: at.height,
    maxWidth: 'none',
    userSelect: 'none' as const,
    pointerEvents: 'none' as const,
    // Past one screen pixel per image pixel, show the pixels instead of blurring them.
    imageRendering: view.zoom >= actual ? ('pixelated' as const) : undefined,
  };
  const paneProps = {
    'data-pane': true,
    onPointerDown,
    onPointerMove,
    onPointerUp,
    onPointerCancel: onPointerUp,
    style: {
      position: 'relative' as const,
      overflow: 'hidden',
      flex: 1,
      minWidth: 0,
      minHeight: 0,
      background: 'black',
      borderRadius: 4,
      touchAction: 'none',
      cursor: view.zoom > 1 ? 'grab' : 'default',
    },
  };
  const label = (text: string, side: 'left' | 'right') => (
    <Text
      size="xs"
      fw={600}
      c="white"
      style={{
        position: 'absolute',
        top: 8,
        [side]: 8,
        padding: '2px 8px',
        borderRadius: 4,
        background: 'rgba(0, 0, 0, 0.6)',
        pointerEvents: 'none',
      }}
    >
      {text}
    </Text>
  );

  if (still === undefined) return null;
  const source = (
    <img
      src={still.source}
      alt={`Original at ${formatDuration(still.at)}`}
      draggable={false}
      onLoad={onLoad(still.source)}
      style={imageStyle}
    />
  );
  const encoded = (
    <img
      src={still.encoded}
      alt={`${after} at ${formatDuration(still.at)}`}
      draggable={false}
      onLoad={onLoad(still.encoded)}
      style={imageStyle}
    />
  );

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      fullScreen
      title={title}
      styles={{
        content: { display: 'flex', flexDirection: 'column' },
        body: { flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 },
      }}
    >
      <Stack gap="xs" style={{ flex: 1, minHeight: 0 }}>
        <Group justify="space-between" gap="xs">
          <Group gap="xs">
            <SegmentedControl
              size="xs"
              value={mode}
              onChange={(value) => setMode(value as Mode)}
              data={[
                { value: 'side', label: 'Side by side' },
                { value: 'swipe', label: 'Swipe' },
              ]}
            />
            {stills.length > 1 && (
              <SegmentedControl
                size="xs"
                value={String(index)}
                onChange={(value) => setIndex(Number(value))}
                data={stills.map((s, i) => ({ value: String(i), label: formatDuration(s.at) }))}
                aria-label="Moment"
              />
            )}
          </Group>
          <Group gap="xs" wrap="nowrap" style={{ flex: '0 1 22rem' }}>
            <Tooltip label="Zoom out (−)">
              <ActionIcon variant="default" aria-label="Zoom out" onClick={() => zoomBy(1 / STEP)}>
                <IconZoomOut size={16} />
              </ActionIcon>
            </Tooltip>
            <Slider
              aria-label="Zoom"
              style={{ flex: 1 }}
              min={1}
              max={MAX_ZOOM}
              step={0.05}
              value={view.zoom}
              onChange={setZoom}
              label={(value) => `${value.toFixed(1)}×`}
            />
            <Tooltip label="Zoom in (+)">
              <ActionIcon variant="default" aria-label="Zoom in" onClick={() => zoomBy(STEP)}>
                <IconZoomIn size={16} />
              </ActionIcon>
            </Tooltip>
            <Button size="compact-xs" variant="default" onClick={() => setView(FIT)}>
              Fit
            </Button>
            <Button size="compact-xs" variant="default" onClick={() => setZoom(actual)}>
              1:1
            </Button>
          </Group>
        </Group>
        <Box
          ref={wheelTarget}
          style={{
            flex: 1,
            minHeight: 0,
            display: 'flex',
            flexDirection: narrow ? 'column' : 'row',
            gap: 8,
            position: 'relative',
          }}
        >
          {mode === 'side' ? (
            <>
              <div ref={paneRef} {...paneProps}>
                {source}
                {label('Original', 'left')}
              </div>
              <div {...paneProps}>
                {encoded}
                {label(after, 'left')}
              </div>
            </>
          ) : (
            <div ref={paneRef} {...paneProps}>
              {source}
              <div
                style={{
                  position: 'absolute',
                  inset: 0,
                  clipPath: `inset(0 0 0 ${divider * 100}%)`,
                  pointerEvents: 'none',
                }}
              >
                {encoded}
              </div>
              {label('Original', 'left')}
              {label(after, 'right')}
              <Divider position={divider} onMove={setDivider} />
            </div>
          )}
          {!ready && (
            <Group
              gap="xs"
              style={{ position: 'absolute', bottom: 12, left: 12, pointerEvents: 'none' }}
            >
              <Loader size="xs" />
              <Text size="xs" c="white">
                Loading full-size stills…
              </Text>
            </Group>
          )}
        </Box>
        <Text size="xs" c="dimmed">
          Drag to move around, scroll or pinch to zoom; ← → switch moments, S switches the view.
          {note && ` ${note}`}
        </Text>
      </Stack>
    </Modal>
  );
}

/** The swipe divider: drag it (or use the arrow keys on it) to show more of either side. */
function Divider({ position, onMove }: { position: number; onMove: (value: number) => void }) {
  const dragging = useRef(false);
  const move = (event: PointerEvent<HTMLDivElement>) => {
    if (!dragging.current) return;
    const box = (event.currentTarget.parentElement as HTMLElement).getBoundingClientRect();
    onMove(Math.min(1, Math.max(0, (event.clientX - box.left) / box.width)));
  };
  return (
    <div
      role="slider"
      tabIndex={0}
      aria-label="Divider"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(position * 100)}
      onPointerDown={(event) => {
        event.stopPropagation(); // the divider, not the image, moves
        event.currentTarget.setPointerCapture(event.pointerId);
        dragging.current = true;
      }}
      onPointerMove={(event) => {
        event.stopPropagation();
        move(event);
      }}
      onPointerUp={() => (dragging.current = false)}
      onPointerCancel={() => (dragging.current = false)}
      onKeyDown={(event) => {
        const step = { ArrowLeft: -0.05, ArrowRight: 0.05 }[event.key];
        if (step === undefined) return;
        event.preventDefault();
        event.stopPropagation();
        onMove(Math.min(1, Math.max(0, position + step)));
      }}
      style={{
        position: 'absolute',
        top: 0,
        bottom: 0,
        left: `calc(${position * 100}% - 16px)`,
        width: 32,
        cursor: 'ew-resize',
        touchAction: 'none',
        display: 'flex',
        justifyContent: 'center',
      }}
    >
      <div style={{ width: 2, background: 'white', boxShadow: '0 0 4px black' }} />
      <div
        style={{
          position: 'absolute',
          top: '50%',
          width: 28,
          height: 28,
          marginTop: -14,
          borderRadius: '50%',
          background: 'white',
          boxShadow: '0 0 6px black',
          color: 'black',
          fontSize: 14,
          lineHeight: '28px',
          textAlign: 'center',
          userSelect: 'none',
        }}
      >
        ⇔
      </div>
    </div>
  );
}
