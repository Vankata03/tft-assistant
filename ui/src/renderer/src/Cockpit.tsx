import { useState } from 'react'
import type {
  EntityDisplay,
  LayoutUnit,
  BaselineContent,
} from '../../shared/messages'
import type { SessionMode } from '../../shared/protocol'
import {
  describeCore,
  describeGameflow,
  type ShellState,
} from '../../shared/state'
import { SessionModeSelector } from './ModeSelector'
import { displayRevision, useShown } from './shown'
import { wispWorthText, wispWorthProvenance } from './wispWorth'
import { augmentReferenceText, augmentReferenceDetails } from './augmentReference'

const TIER_ORDER: Record<string, number> = {
  'S+': 0,
  S: 1,
  A: 2,
  B: 3,
  C: 4,
  D: 5,
}

export interface CockpitProps {
  state: ShellState
  onSelectGuide(id: string): void
  onMode(mode: SessionMode): void
}

export function EntityName({
  entity,
  small = false,
}: {
  entity: EntityDisplay
  small?: boolean
}): React.JSX.Element {
  return (
    <span className={`entity ${small ? 'entity-small' : ''}`}>
      {entity.icon ? (
        <img
          src={entity.icon}
          alt=""
          loading="lazy"
          onError={(event) => {
            event.currentTarget.hidden = true
          }}
        />
      ) : (
        <span className="entity-initial" aria-hidden="true">
          {entity.name.slice(0, 2)}
        </span>
      )}
      <span>{entity.name}</span>
    </span>
  )
}

export function Layout({
  title,
  units,
}: {
  title: string
  units: readonly LayoutUnit[]
}): React.JSX.Element {
  const unplaced = units.filter((unit) => unit.position === null)
  return (
    <section className="panel layout-panel">
      <h2>
        {title}
        <span className="subtle">4 × 7</span>
      </h2>
      <div className="hex-board" aria-label={title}>
        {Array.from({ length: 4 }, (_, row) => (
          <div className={`hex-row row-${row}`} key={row}>
            {Array.from({ length: 7 }, (_, col) => {
              const position = row * 7 + col
              const unit = units.find((unit) => unit.position === position)
              return (
                <div
                  key={position}
                  className={`hex ${unit ? 'occupied' : ''}`}
                  title={unit?.entity.name ?? `Hex ${position + 1}`}
                >
                  {unit ? (
                    <span>
                      {unit.entity.icon ? (
                        <img src={unit.entity.icon} alt={unit.entity.name} />
                      ) : (
                        unit.entity.name.slice(0, 2)
                      )}
                    </span>
                  ) : null}
                </div>
              )
            })}
          </div>
        ))}
      </div>
      {unplaced.length > 0 ? (
        <>
          <p className="subtle">Unplaced · source layout unavailable</p>
          <div className="unit-legend">
            {unplaced.map((unit) => (
              <EntityName key={unit.entity.id} entity={unit.entity} small />
            ))}
          </div>
        </>
      ) : (
        <div className="unit-legend">
          {units.map((unit) => (
            <EntityName key={unit.entity.id} entity={unit.entity} small />
          ))}
        </div>
      )}
    </section>
  )
}

function GuideRail({
  content,
  onSelectGuide,
}: {
  content: BaselineContent
  onSelectGuide(id: string): void
}): React.JSX.Element {
  const [search, setSearch] = useState('')
  const guides = content.guides.filter((guide) =>
    `${guide.name} ${guide.units.map((u) => u.name).join(' ')}`
      .toLowerCase()
      .includes(search.toLowerCase()),
  )
  return (
    <aside className="panel guide-rail">
      <h2>Guides</h2>
      <label className="sr-only" htmlFor="guide-search">
        Search Guides
      </label>
      <input
        id="guide-search"
        type="search"
        placeholder="Search Guides…"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
      />
      <div className="guide-list">
        {guides.map((guide) => (
          <button
            key={guide.id}
            className={`guide-choice ${content.selected?.id === guide.id ? 'selected' : ''}`}
            aria-pressed={content.selected?.id === guide.id}
            onClick={() => onSelectGuide(guide.id)}
          >
            <span>
              {guide.name}
              <small>
                {guide.units
                  .slice(0, 3)
                  .map((u) => u.name)
                  .join(' · ')}
              </small>
            </span>
            <strong className="tier">{guide.tier}</strong>
          </button>
        ))}
      </div>
      {guides.length === 0 ? (
        <p className="subtle">No Guides available.</p>
      ) : null}
      <p className="rail-note">
        Choose a Guide. Tiers come from the data source.
      </p>
    </aside>
  )
}

function ReferencePanels({
  content,
}: {
  content: BaselineContent
}): React.JSX.Element {
  const [allAugments, setAllAugments] = useState(false)
  const [wispSearch, setWispSearch] = useState('')
  const augments = [...content.augments].sort(
    (a, b) =>
      Number(b.offered) - Number(a.offered) ||
      Number(b.in_guide) - Number(a.in_guide) ||
      (a.average_placement !== null && b.average_placement !== null ? a.average_placement - b.average_placement : Number(a.average_placement === null) - Number(b.average_placement === null)) ||
      (TIER_ORDER[a.tier ?? ''] ?? 99) - (TIER_ORDER[b.tier ?? ''] ?? 99) ||
      a.entity.name.localeCompare(b.entity.name),
  )
  const wisps = content.wisps.filter((wisp) =>
    wisp.entity.name.toLowerCase().includes(wispSearch.toLowerCase()),
  )
  useShown(
    'cockpit',
    displayRevision(content.snapshot_id, 'reference', {
      augments: allAugments ? augments : augments.slice(0, 8),
      wisps: wisps.slice(0, 10),
      faced: content.faced,
    }),
  )
  return (
    <aside className="reference-column">
      <section className="panel">
        <h2>Augment references</h2>
        <div className="reference-rows">
          {(allAugments ? augments : augments.slice(0, 8)).map((row) => (
            <div
              className={`reference-row ${row.offered ? 'offered' : ''}`}
              key={row.entity.id}
            >
              <strong className="tier" title={augmentReferenceDetails(row)}>{augmentReferenceText(row)}</strong>
              <EntityName entity={row.entity} small />
              <span className="in-guide">{row.in_guide ? 'In Guide' : ''}</span>
            </div>
          ))}
        </div>
        {augments.length === 0 ? (
          <p className="subtle">Augment references unavailable.</p>
        ) : null}
        {augments.length > 8 ? (
          <button
            className="text-button"
            onClick={() => setAllAugments(!allAugments)}
          >
            {allAugments
              ? 'Show fewer references'
              : `Show all ${augments.length} references`}
          </button>
        ) : null}
        <p className="subtle">
          Qualified comp statistics take precedence over global statistics. Tiers remain the fallback.
        </p>
      </section>
      <section className="panel">
        <h2>
          Wisp worth <span className="subtle">Static</span>
        </h2>
        <label className="sr-only" htmlFor="wisp-search">
          Search Wisp worth
        </label>
        {content.wisps.length > 10 ? (
          <input
            id="wisp-search"
            type="search"
            placeholder="Search Wisps…"
            value={wispSearch}
            onChange={(event) => setWispSearch(event.target.value)}
          />
        ) : null}
        <table>
          <thead>
            <tr>
              <th>Wisp</th>
              <th>Worth</th>
            </tr>
          </thead>
          <tbody>
            {wisps.slice(0, 10).map((row) => (
              <tr key={row.entity.id}>
                <td>
                  <EntityName entity={row.entity} small />
                </td>
                <td title={wispWorthProvenance(row)}>
                  {wispWorthText(row)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {content.wisps.length === 0 ? (
          <p className="subtle">Offline worth table unavailable.</p>
        ) : null}
        {wisps.length > 10 ? (
          <p className="subtle">
            Showing 10 of {wisps.length}. Search to find a Wisp.
          </p>
        ) : null}
      </section>
      <section className="panel">
        <h2>Opponents faced</h2>
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Result</th>
            </tr>
          </thead>
          <tbody>
            {content.faced.map((row, index) => (
              <tr key={index}>
                <td>{row.name}</td>
                <td className={`result-${row.result}`}>{row.result}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {content.faced.length === 0 ? (
          <p className="subtle">No confirmed fight results.</p>
        ) : null}
      </section>
    </aside>
  )
}

export function Cockpit({
  state,
  onSelectGuide,
  onMode,
}: CockpitProps): React.JSX.Element {
  const view =
    state.core === 'running' && state.baseline?.mode === state.mode
      ? state.baseline
      : null
  const content = state.mode === 'baseline' ? view?.content : null
  const guide = content?.selected
  useShown(
    'cockpit',
    content
      ? displayRevision(content.snapshot_id, 'guide', {
          guides: content.guides,
          selected: guide,
          xp: content.xp_hint,
          par: content.par,
          shop: content.shop,
          recipes: content.recipes,
        })
      : null,
  )
  return (
    <main className="cockpit">
      <header className="app-header">
        <h1>TFT Assistant</h1>
        <SessionModeSelector state={state} onChange={onMode} />
        <span className="connection">{describeCore(state.core)}</span>
        {content ? <span className="patch">Patch {content.patch}</span> : null}
      </header>
      {state.error ? (
        <p className="status-banner" role="alert">
          {state.error}
        </p>
      ) : null}
      {view?.stale.length ? (
        <div className="status-banner paused" role="status">
          {view.stale.map((row) => (
            <span key={row.field}>
              {row.reason}
              {row.age_seconds === null
                ? ''
                : ` · ${Math.round(row.age_seconds)}s`}
            </span>
          ))}
        </div>
      ) : null}
      {content ? (
        <div className="cockpit-grid">
          <GuideRail content={content} onSelectGuide={onSelectGuide} />
          <div className="guide-column">
            <section className="panel guide-heading">
              <h2>{guide?.name ?? 'Choose your Guide'}</h2>
              <div className="plan-strip">
                <div
                  className={`par-chip ${content.par.probability === null || content.par.uncertain ? 'paused' : ''}`}
                >
                  <span>Par win chance</span>
                  <strong>
                    {content.par.probability === null
                      ? 'Paused'
                      : `${Math.round(content.par.probability * 100)}%${content.par.uncertain ? ' ?' : ''}`}
                  </strong>
                  {content.par.paused ? (
                    <small>{content.par.paused}</small>
                  ) : null}
                </div>
                <div>
                  <span className="subtle">Guide stage plan</span>
                  <p>
                    {content.xp_hint?.text ??
                      (guide
                        ? 'XP hint unavailable · no readable XP or explicit Guide target'
                        : 'Select a Guide to see its plan.')}
                  </p>
                  {content.xp_hint ? (
                    <small className="subtle">
                      Includes {content.xp_hint.passive_xp} passive XP by the
                      target round.
                    </small>
                  ) : null}
                </div>
              </div>
              {guide ? (
                <div className="stage-tips">
                  {Object.entries(guide.stage_tips).map(([stage, tip]) => (
                    <p key={stage}>
                      <strong>Stage {stage}</strong> {tip}
                    </p>
                  ))}
                </div>
              ) : null}
              {guide?.stage_plan.length ? (
                <div className="stage-tips">
                  {guide.stage_plan.map((step, index) => (
                    <p key={index}>
                      <strong>{String(step.round ?? 'Guide step')}</strong>
                      {step.level !== undefined
                        ? ` Level target ${step.level}.`
                        : ''}
                      {step.roll_level !== undefined
                        ? ` Roll plan at level ${step.roll_level}.`
                        : ''}
                      {step.gold_floor !== undefined
                        ? ` Gold floor ${step.gold_floor}.`
                        : ''}
                    </p>
                  ))}
                </div>
              ) : null}
            </section>
            {guide ? (
              <>
                <div className="layouts">
                  <Layout title="Early layout" units={guide.early_layout} />
                  <Layout title="Final layout" units={guide.final_layout} />
                </div>
                <div className="bottom-panels">
                  <section className="panel recipes">
                    <h2>Best-in-slot &amp; recipes</h2>
                    <table>
                      <thead>
                        <tr>
                          <th>Unit</th>
                          <th>Item</th>
                          <th>Recipe</th>
                        </tr>
                      </thead>
                      <tbody>
                        {content.recipes.map((row, index) => (
                          <tr key={index}>
                            <td>
                              <EntityName entity={row.unit} small />
                            </td>
                            <td>
                              <EntityName entity={row.item} small />
                            </td>
                            <td className="recipe-parts">
                              {row.components.length ? (
                                row.components.map((part, i) => (
                                  <span
                                    key={i}
                                    className={part.held ? 'held' : ''}
                                  >
                                    {i > 0 ? (
                                      <span className="recipe-plus">+</span>
                                    ) : null}
                                    <EntityName entity={part.entity} small />
                                    {part.held ? <small>held</small> : null}
                                  </span>
                                ))
                              ) : (
                                <span className="subtle">
                                  Recipe unavailable
                                </span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {content.recipes.length === 0 ? (
                      <p className="subtle">Guide item data unavailable.</p>
                    ) : null}
                  </section>
                  <section className="panel carousel">
                    <h2>Carousel priorities</h2>
                    <ol>
                      {guide.carousel.map((row) => (
                        <li key={row.id}>
                          <EntityName entity={row} small />
                        </li>
                      ))}
                    </ol>
                    {guide.carousel.length === 0 ? (
                      <p className="subtle">Guide priorities unavailable.</p>
                    ) : null}
                  </section>
                </div>
                {guide.alternatives.length ? (
                  <section className="panel">
                    <h2>Guide alternatives</h2>
                    <div className="alternatives">
                      {guide.alternatives.map((id) => (
                        <button
                          key={id}
                          disabled={!content.guides.some((g) => g.id === id)}
                          onClick={() => onSelectGuide(id)}
                        >
                          {content.guides.find((g) => g.id === id)?.name ?? id}
                        </button>
                      ))}
                    </div>
                  </section>
                ) : null}
              </>
            ) : (
              <section className="empty-guide">
                <p>Choose a Guide from the list.</p>
                <p className="subtle">
                  Its plan, layouts, recipes and priorities will stay visible
                  together.
                </p>
              </section>
            )}
            {content.shop.length ? (
              <section className="panel shop-reference">
                <h2>Shop highlights</h2>
                <div>
                  {content.shop.map((row) => (
                    <span
                      className={row.in_guide ? 'in-guide' : 'subtle'}
                      key={row.slot}
                    >
                      Slot {row.slot + 1}: {row.entity.name}
                      {row.in_guide ? ' · In Guide' : ''}
                    </span>
                  ))}
                </div>
              </section>
            ) : null}
          </div>
          <ReferencePanels content={content} />
        </div>
      ) : (
        <section className="status-only" role="status">
          <span className="status-dot" />
          <h2>
            {state.core !== 'running'
              ? describeCore(state.core)
              : state.mode === 'silent'
                ? state.gameflow?.clientRunning && ['InProgress','Reconnect','PreEndOfGame'].includes(state.gameflow.phase??'')
                  ? 'Silent game · capture status below'
                  : 'Silent mode · waiting for a game'
                : state.mode === 'live'
                  ? 'Live surface unavailable'
                  : 'Baseline data unavailable'}
          </h2>
          <p>
            {view?.status ??
              (state.core === 'running'
                ? 'Waiting for validated data and capture status.'
                : 'Waiting for the core connection.')}
          </p>
        </section>
      )}
      <footer>
        <span>{view?.status ?? describeGameflow(state)}</span>
        {content ? (
          <>
            <span>Round {content.round_id ?? 'unread'}</span>
            <span>Data snapshot {content.snapshot_id.slice(0, 12)}</span>
          </>
        ) : null}
      </footer>
      {content?.warnings.length ? (
        <details className="data-warnings">
          <summary>Data qualifications ({content.warnings.length})</summary>
          {content.warnings.map((warning, index) => (
            <p key={index}>{warning}</p>
          ))}
        </details>
      ) : null}
    </main>
  )
}
