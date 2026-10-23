export const pct = (v: number | null | undefined, digits = 0): string =>
  v === null || v === undefined ? '—' : `${(v * 100).toFixed(digits)}%`

export const date = (iso: string | null | undefined): string =>
  iso ? new Date(iso).toLocaleDateString(undefined, { day: '2-digit', month: 'short' }) : '—'

export const dateTime = (iso: string | null | undefined): string =>
  iso ? new Date(iso).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' }) : '—'

const LOW = [235, 104, 52] // orange
const MID = [163, 162, 156] // neutral gray
const HIGH = [42, 120, 214] // blue

/** Diverging scale for a 0..1 score: orange (low) → gray (0.5) → blue (high). */
export function heat(score: number | null | undefined): string {
  if (score === null || score === undefined) return 'var(--node-empty)'
  const s = Math.max(0, Math.min(1, score))
  const [a, b, t] = s < 0.5 ? [LOW, MID, s / 0.5] : [MID, HIGH, (s - 0.5) / 0.5]
  const mix = a.map((v, i) => Math.round(v + (b[i] - v) * t))
  return `rgb(${mix.join(' ')})`
}

/** Sequential one-hue scale (light → dark blue) for magnitudes such as mastery. */
export function seq(score: number | null | undefined): string {
  if (score === null || score === undefined) return 'transparent'
  const s = Math.max(0, Math.min(1, score))
  return `color-mix(in oklab, var(--series-1) ${Math.round(15 + s * 85)}%, var(--surface))`
}

export const STATUS_LABEL: Record<string, string> = {
  draft: 'Draft — upload a book',
  indexing: 'Extracting the index…',
  review: 'Index review',
  building: 'Building the graph…',
  growing: 'Growing',
  complete: 'Complete',
  frozen: 'Frozen'
}

export const OUTCOME_LABEL: Record<string, string> = {
  pending: 'Thinking…',
  created_node: 'Created a new node',
  linked_existing: 'Linked to an existing node',
  answered_only: 'Answered',
  failed: 'Failed'
}
