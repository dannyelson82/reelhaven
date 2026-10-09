import { FIT, actualPixels, clamp, pan, placement, shown, zoomTo } from './compareView';

const pane = { width: 1000, height: 500 };
const image = { width: 3840, height: 1600 }; // wider than the pane: fits by width

it('fits the whole image at zoom 1', () => {
  const size = shown(pane, image, 1);
  expect(size.width).toBeCloseTo(1000);
  expect(size.height).toBeCloseTo(1000 * (1600 / 3840));
  const at = placement(FIT, pane, image);
  expect(at.left).toBeCloseTo(0);
  expect(at.width).toBeCloseTo(1000);
  expect(at.top).toBeCloseTo((500 - at.height) / 2);
});

it('knows the zoom for actual pixels', () => {
  expect(actualPixels(pane, image)).toBeCloseTo(3.84);
  expect(actualPixels(pane, { width: 400, height: 200 })).toBe(1); // never below fit
});

it('keeps the image covering the pane when zoomed in', () => {
  const view = clamp({ zoom: 1.1, cx: 0, cy: 0 }, pane, image);
  const at = placement(view, pane, image);
  expect(at.left).toBeCloseTo(0);
  expect(view.cy).toBe(0.5); // still shorter than the pane: centred
  expect(clamp({ zoom: 20, cx: 0.5, cy: 0.5 }, pane, image).zoom).toBe(8);
  expect(clamp({ zoom: 0.2, cx: 0.9, cy: 0.5 }, pane, image)).toEqual(FIT);
});

it('pans by screen pixels', () => {
  const view = pan({ zoom: 2, cx: 0.5, cy: 0.5 }, -200, 0, pane, image);
  expect(view.cx).toBeCloseTo(0.6); // dragged left by 200 of 2000 pixels
  expect(pan(FIT, -200, 0, pane, image)).toEqual(FIT); // nothing to pan at fit
});

it('zooms around the pointer', () => {
  // The image point under x = 750 stays under it.
  const view = zoomTo(FIT, 2, pane, image, 750, 250);
  const at = placement(view, pane, image);
  expect((750 - at.left) / at.width).toBeCloseTo(0.75);
  expect(zoomTo(FIT, 2, pane, image).cx).toBe(0.5); // the centre by default
});

it('shows the same spot in panes of different sizes', () => {
  const view = { zoom: 3, cx: 0.3, cy: 0.6 };
  const small = { width: 600, height: 400 };
  for (const p of [pane, small]) {
    const at = placement(view, p, image);
    expect((p.width / 2 - at.left) / at.width).toBeCloseTo(0.3);
    expect((p.height / 2 - at.top) / at.height).toBeCloseTo(0.6);
  }
});
