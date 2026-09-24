export type Point = [number, number];

export function jointEnd(x: number, y: number, angle: number, length: number): Point {
  return [x - Math.sin(angle) * length, y + Math.cos(angle) * length];
}

// Place the atlas crop around its own centre. Native views must have a real
// frame; nesting rotated zero-size views gives different pivots on iOS.
export function spriteFrame(rect: number[], anchor: Point, scale: number, pivot: Point, rotation: number) {
  const width = rect[2] * scale, height = rect[3] * scale;
  const dx = (rect[0] - anchor[0]) * scale + width / 2;
  const dy = (rect[1] - anchor[1]) * scale + height / 2;
  return {
    left: pivot[0] + dx * Math.cos(rotation) - dy * Math.sin(rotation) - width / 2,
    top: pivot[1] + dx * Math.sin(rotation) + dy * Math.cos(rotation) - height / 2,
    width, height,
  };
}
