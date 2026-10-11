import type { WispWorth } from '../../shared/messages'

export function wispWorthText(row: WispWorth): string {
  if (row.worth_label === 'unavailable') return 'Unavailable'
  if (row.worth_label) {
    const labels = { worth_it: 'Worth it', situational: 'Situational', skip: 'Skip' }
    const stage = row.worth_stage ? `Stage ${row.worth_stage} · ` : ''
    return `${stage}${labels[row.worth_label]}`
  }
  return row.worth === null ? 'Unavailable' : String(row.worth)
}
