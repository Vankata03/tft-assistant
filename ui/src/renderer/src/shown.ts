import { useEffect } from 'react'

/** Stable display revision; logs identify the validated snapshot and the rendered piece. */
export function displayRevision(
  snapshot: string,
  piece: string,
  value: unknown,
): string {
  let hash = 2166136261
  for (const character of JSON.stringify(value)) {
    hash ^= character.charCodeAt(0)
    hash = Math.imul(hash, 16777619)
  }
  return `${snapshot}:${piece}:${(hash >>> 0).toString(16)}`
}

export function useShown(
  surface: 'cockpit' | 'overlay',
  revision: string | null,
): void {
  useEffect(() => {
    if (!revision || typeof window === 'undefined') return
    // Deferral avoids reporting StrictMode's discarded render as a shown surface.
    const timer = setTimeout(
      () =>
        window.coach?.reportShown(surface, revision, new Date().toISOString()),
      0,
    )
    return () => clearTimeout(timer)
  }, [surface, revision])
}
