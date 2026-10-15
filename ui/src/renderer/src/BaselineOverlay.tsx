import type { ShellState } from '../../shared/state'
import { displayRevision, useShown } from './shown'
import { wispWorthText, wispWorthProvenance } from './wispWorth'
import { augmentReferenceText, augmentReferenceDetails } from './augmentReference'

export function BaselineOverlay({
  state,
}: {
  state: ShellState
}): React.JSX.Element | null {
  const content =
    state.core === 'running' &&
    state.mode === 'baseline' &&
    state.baseline?.mode === 'baseline'
      ? state.baseline.content
      : null
  const anchors=state.overlayGeometry?.bounds?state.overlayGeometry.anchors.filter(row=>['shop','level','par','augment','carousel','wisp'].includes(row.kind)):content?.overlay_allowed&&content.overlay_bounds?content.anchors:[]
  const tags =
    content
      ? anchors.flatMap((anchor) => {
          let text: string | null = null
          let paused = false
          let details: string | null = null
          if (
            anchor.kind === 'shop' &&
            ['planning', 'roll_down'].includes(content.phase)
          ) {
            const row = content.shop.find((row) => row.slot === anchor.index)
            if (row?.in_guide) text = 'In Guide'
          } else if (anchor.kind === 'par' && content.phase === 'planning') {
            text =
              content.par.probability === null
                ? `paused · ${content.par.paused ?? 'own board unread'}`
                : `Par win chance ${Math.round(content.par.probability * 100)}%${content.par.uncertain ? ' ?' : ''}`
            paused = content.par.probability === null || content.par.uncertain
          } else if (
            anchor.kind === 'level' &&
            ['planning', 'combat'].includes(content.phase)
          ) {
            const stage = content.round_id?.split('-')[0]
            text =
              content.phase === 'combat'
                ? (content.selected?.stage_tips[String(Number(stage) + 1)] ??
                  null)
                : (content.xp_hint?.text ?? null)
          } else if (anchor.kind === 'augment' && content.phase === 'augment') {
            const row = content.augments.find(
              (row) => row.offer_index === anchor.index,
            )
            if (row) {
              text = `${augmentReferenceText(row)}${row.in_guide ? ' · In Guide' : ''}`
              details = augmentReferenceDetails(row)
            }
          } else if (anchor.kind === 'wisp' && content.phase === 'planning') {
            const row = content.wisps.find(
              (row) => row.offered_slot === anchor.index,
            )
            if (row) {
              const worth = wispWorthText(row)
              details = wispWorthProvenance(row)
              paused = worth === 'Unavailable'
              text = paused
                ? 'paused · static Wisp worth unavailable'
                : `Static worth ${worth}`
            }
          } else if (
            anchor.kind === 'carousel' &&
            content.phase === 'carousel' &&
            content.selected
          ) {
            text = `Guide priority: ${content.selected.carousel.map((row) => row.name).join(' · ')}`
          }
          return text ? [{ anchor, text, paused, details }] : []
        })
      : []
  useShown(
    'overlay',
    content && tags.length
      ? displayRevision(content.snapshot_id, 'overlay', tags)
      : null,
  )
  if (!tags.length) return null
  return (
    <div className="baseline-overlay" aria-label="Baseline overlay">
      {tags.map(({ anchor, text, paused, details }, index) => (
        <div
          key={index}
          className={`overlay-tag ${paused ? 'paused' : ''}`}
          style={{
            left: `${anchor.x * 100}%`,
            top: `${anchor.y * 100}%`,
            width: `${anchor.width * 100}%`,
            minHeight: `${anchor.height * 100}vh`,
          }}
          title={details ? `${text} · ${details}` : text}
        >
          {text}
          <span className="overlay-tooltip">{details ? `${text} · ${details}` : text}</span>
        </div>
      ))}
    </div>
  )
}
