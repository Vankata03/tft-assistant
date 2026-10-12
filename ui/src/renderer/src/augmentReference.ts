import type { AugmentTier } from '../../shared/messages'

export function augmentReferenceText(row: AugmentTier): string {
  return row.average_placement === null ? `Tier ${row.tier ?? 'unavailable'}` : `Avg ${row.average_placement.toFixed(2)}`
}

export function augmentReferenceDetails(row: AugmentTier): string {
  if (row.average_placement === null) return 'Tier reference; qualified statistics unavailable'
  return [row.statistic_scope === 'comp' ? 'Comp' : 'Global',
    row.pick_stage === null ? 'All picks' : `Pick ${row.pick_stage}`, `${row.sample_count} games`,
    `Source: ${row.statistic_source}`, row.stale ? 'stale' : '', row.changed ? 'changed' : ''].filter(Boolean).join(' · ')
}
