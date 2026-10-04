// Tray icons drawn in code: a filled disc per session mode, a ring while the
// core is not connected. Silent is grey, Baseline blue, Live red.
import { nativeImage, type NativeImage } from 'electron'
import type { SessionMode } from '../shared/protocol'

type Rgb = readonly [number, number, number]

const COLORS: Record<SessionMode, Rgb> = {
  silent: [140, 140, 140],
  baseline: [40, 120, 230],
  live: [225, 50, 40],
}
const UNKNOWN: Rgb = [140, 140, 140]

/** BGRA pixels of an anti-aliased disc, or a ring when `ring` is set. */
function drawDisc(size: number, [r, g, b]: Rgb, ring: boolean): Buffer {
  const pixels = Buffer.alloc(size * size * 4)
  const center = size / 2
  const outer = size / 2 - 0.5
  const inner = ring ? outer - size / 5 : -1
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const d = Math.hypot(x + 0.5 - center, y + 0.5 - center)
      const coverage = Math.min(Math.max(outer - d + 0.5, 0), 1) * Math.min(Math.max(d - inner + 0.5, 0), 1)
      const i = (y * size + x) * 4
      pixels[i] = b
      pixels[i + 1] = g
      pixels[i + 2] = r
      pixels[i + 3] = Math.round(coverage * 255)
    }
  }
  return pixels
}

export function trayIcon(mode: SessionMode | null): NativeImage {
  const color = mode ? COLORS[mode] : UNKNOWN
  const image = nativeImage.createFromBitmap(drawDisc(16, color, mode === null), { width: 16, height: 16 })
  image.addRepresentation({
    scaleFactor: 2,
    width: 32,
    height: 32,
    buffer: drawDisc(32, color, mode === null),
  })
  return image
}
