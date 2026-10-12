import type { WispWorth } from '../../shared/messages'

export function wispWorthText(row: WispWorth): string {
  if (row.worth_label === 'unavailable') return 'Unavailable'
  if (row.worth_label) {
    const labels = { worth_it: 'Worth it', situational: 'Situational', skip: 'Skip' }
    const stage = row.worth_stage ? `Stage ${row.worth_stage} · ` : ''
    const reference = row.reference_source === 'owner' ? ' · Owner override'
      : row.reference_source === 'engine_standard_state' ? ' · Standard state reference' : ''
    return `${stage}${labels[row.worth_label]}${reference}`
  }
  return row.worth === null ? 'Unavailable' : String(row.worth)
}

export function wispWorthProvenance(row: WispWorth): string {
  return row.reference_source ? `Reference source: ${row.reference_source} · Table source: ${row.source}` : `Source: ${row.source}`
}
