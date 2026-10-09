/** Geometry of the comparison viewer. Both images are the same size, so one view (zoom and
 * the image point at the centre of the pane) places either of them; panes of different
 * sizes still show the same spot. */

export interface View {
  /** 1 = the whole image fits the pane. */
  zoom: number;
  /** The image point shown at the centre of the pane, as fractions of its width and height. */
  cx: number;
  cy: number;
}

export interface Size {
  width: number;
  height: number;
}

export const FIT: View = { zoom: 1, cx: 0.5, cy: 0.5 };
export const MAX_ZOOM = 8;

/** The image's on-screen size at a zoom. */
export function shown(pane: Size, image: Size, zoom: number): Size {
  const fit = Math.min(pane.width / image.width, pane.height / image.height) || 1;
  return { width: image.width * fit * zoom, height: image.height * fit * zoom };
}

/** The zoom at which one image pixel is one screen pixel. */
export function actualPixels(pane: Size, image: Size): number {
  return Math.min(MAX_ZOOM, Math.max(1, image.width / shown(pane, image, 1).width));
}

function clampAxis(centre: number, paneLength: number, shownLength: number): number {
  if (shownLength <= paneLength) return 0.5; // smaller than the pane: keep it centred
  const half = paneLength / 2 / shownLength;
  return Math.min(1 - half, Math.max(half, centre));
}

/** Keeps the image covering the pane once it is larger than it. */
export function clamp(view: View, pane: Size, image: Size): View {
  const zoom = Math.min(MAX_ZOOM, Math.max(1, view.zoom));
  const size = shown(pane, image, zoom);
  return {
    zoom,
    cx: clampAxis(view.cx, pane.width, size.width),
    cy: clampAxis(view.cy, pane.height, size.height),
  };
}

/** Drags the image by a number of screen pixels. */
export function pan(view: View, dx: number, dy: number, pane: Size, image: Size): View {
  const size = shown(pane, image, view.zoom);
  return clamp(
    { ...view, cx: view.cx - dx / size.width, cy: view.cy - dy / size.height },
    pane,
    image,
  );
}

/** Changes the zoom, keeping the image point under (x, y) in the pane where it is
 * (the centre of the pane when no point is given). */
export function zoomTo(view: View, zoom: number, pane: Size, image: Size, x?: number, y?: number) {
  const offsetX = (x ?? pane.width / 2) - pane.width / 2;
  const offsetY = (y ?? pane.height / 2) - pane.height / 2;
  const before = shown(pane, image, view.zoom);
  const pointX = view.cx + offsetX / before.width;
  const pointY = view.cy + offsetY / before.height;
  const after = shown(pane, image, Math.min(MAX_ZOOM, Math.max(1, zoom)));
  return clamp(
    { zoom, cx: pointX - offsetX / after.width, cy: pointY - offsetY / after.height },
    pane,
    image,
  );
}

/** Where to draw the image in the pane (CSS pixels). */
export function placement(view: View, pane: Size, image: Size) {
  const size = shown(pane, image, view.zoom);
  return {
    left: pane.width / 2 - view.cx * size.width,
    top: pane.height / 2 - view.cy * size.height,
    width: size.width,
    height: size.height,
  };
}
