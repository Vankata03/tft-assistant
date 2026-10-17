import { useEffect, useRef, useState } from "react";
import { describeSchedule } from "../lineSchedule";

type Path = (string | number)[];
type RecordValue = Record<string, unknown>;
export interface ReviewSectionProps {
  name: string;
  /** Change this when the authenticated report or mode epoch changes. Callback identity may change within that scope. */
  scopeKey?: string;
  path: Path;
  request: (
    operation: "page",
    args: { path: Path; cursor: number; limit: number },
  ) => Promise<RecordValue>;
  onDebug: (path: Path) => void;
}
const object = (value: unknown): RecordValue =>
  value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as RecordValue)
    : {};
const number = (value: unknown): number | null =>
  typeof value === "number" && Number.isFinite(value) ? value : null;
const text = (value: unknown): string =>
  typeof value === "string" || typeof value === "boolean"
    ? String(value)
    : (number(value)?.toString() ?? "Unavailable");
const fields = new Set([
  "round_id",
  "log_seq",
  "observed",
  "recommended",
  "actual",
  "pin",
  "pinned",
  "pin_cost",
  "followed",
  "fight_path",
  "shown_option_id",
  "shown_at",
  "delivery_revision",
  "surfaces",
  "cause",
  "would_have_said",
  "unavailable",
  "evidence_path",
  "line_id",
  "schedule",
  "id",
  "levels",
  "rolls",
  "observed_rolls",
  "death_placement_cost",
  "expected_placement",
  "standard_error",
  "death_probability",
  "hit_probability",
  "confidence",
  "projections",
  "gold",
  "level",
  "hp",
  "planned_gold",
  "status",
  "target",
  "candidates",
  "backup",
  "called_status",
  "observed_lock",
  "pivot_from",
  "pivot_to",
  "pivot_round",
  "rejected_target",
  "player_label",
  "divergence_round",
  "planning_round",
  "target_similarity",
  "opponent_id",
  "start_log_seq",
  "start_at",
  "result",
  "actual_hp_loss",
  "win_probability",
  "predicted_hp_loss",
  "opponent_warning",
  "winner_unit_count",
  "winner_unit_count_source",
  "moment_id",
  "engine_decision_id",
  "category",
  "cost",
  "paired_uncertainty",
  "close_call",
  "differed",
  "shown",
  "reason",
  "action",
  "layout",
  "unit_index",
  "unit_id",
  "cell",
  // Full-timeline capture gap rows.
  "kind",
  "start",
  "end",
  "start_round_id",
  "end_round_id",
  "unreviewed_snapshot_count",
]);
// Round-keyed maps and reason maps keep every recorded key.
const openMaps = new Set(["observed", "unavailable", "levels", "rolls", "observed_rolls"]);
function normalValue(value: unknown, field?: string): unknown {
  if (Array.isArray(value)) return value.map((child) => normalValue(child));
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value)
        .filter(([key]) => fields.has(key) || openMaps.has(field ?? ""))
        .map(([key, child]) => [key, normalValue(child, key)]),
    );
  }
  return value;
}

const same = (a: unknown, b: Path): boolean =>
  Array.isArray(a) &&
  a.length === b.length &&
  a.every((key, index) => key === b[index]);

async function readMember(
  request: ReviewSectionProps["request"],
  path: Path,
  budget: { left: number },
  depth = 0,
): Promise<unknown> {
  if (depth > 8)
    throw new Error("Review section exceeds the supported nesting depth");
  let cursor = 0;
  let kind: unknown;
  const result: RecordValue = Object.create(null);
  const array: unknown[] = [];
  do {
    if (--budget.left < 0)
      throw new Error("Review section exceeds the page budget");
    const page = await request("page", { path, cursor, limit: 16 });
    if (
      !same(page.path, path) ||
      !["array", "object", "value", "string"].includes(String(page.kind)) ||
      (kind !== undefined && kind !== page.kind) ||
      !Array.isArray(page.items)
    )
      throw new Error("Invalid review section page");
    kind = page.kind;
    for (const raw of page.items) {
      const item = object(raw);
      const member = item.path;
      if (kind === "value" || kind === "string") {
        if (!same(member, path) || item.reference === true)
          throw new Error("Invalid review value page");
        if (kind === "value") return normalValue(item.value);
        return "Long text available in Debug";
      }
      if (!Array.isArray(member) || !same(member.slice(0, -1), path))
        throw new Error("Invalid review member path");
      const key = member[member.length - 1];
      if (kind === "array" && (!Number.isInteger(key) || key !== array.length))
        throw new Error("Invalid review array member");
      if (kind === "object" && typeof key !== "string")
        throw new Error("Invalid review object member");
      // Normal surfaces never expand schedules, rollout distributions or unknown fields.
      if (
        kind === "object" &&
        !fields.has(key) &&
        !openMaps.has(String(path.at(-1)))
      )
        continue;
      const value =
        item.reference === true
          ? await readMember(request, member as Path, budget, depth + 1)
          : normalValue(item.value, key as string);
      if (kind === "array") array.push(value);
      else result[key as string] = value;
    }
    if (page.next_cursor === null || page.next_cursor === undefined) break;
    if (
      !Number.isInteger(page.next_cursor) ||
      (page.next_cursor as number) <= cursor
    )
      throw new Error("Invalid review page cursor");
    cursor = page.next_cursor as number;
  } while (true);
  return kind === "array" ? array : result;
}

async function readRows(
  request: ReviewSectionProps["request"],
  path: Path,
  cursor: number,
): Promise<{ rows: unknown[]; next: number | null }> {
  const page = await request("page", { path, cursor, limit: 8 });
  if (
    !same(page.path, path) ||
    page.kind !== "array" ||
    !Array.isArray(page.items) ||
    page.items.length > 8
  )
    throw new Error("Invalid review section page");
  const rows: unknown[] = [];
  const budget = { left: 256 };
  for (const raw of page.items) {
    const item = object(raw);
    const member = [...path, cursor + rows.length];
    if (!same(item.path, member)) throw new Error("Invalid review row path");
    rows.push(
      item.reference === true
        ? await readMember(request, member, budget)
        : normalValue(item.value),
    );
  }
  const next = page.next_cursor ?? null;
  if (
    next !== null &&
    (!Number.isInteger(next) ||
      next !== cursor + rows.length ||
      rows.length === 0)
  )
    throw new Error("Invalid review page cursor");
  return { rows, next: next as number | null };
}

function Forecast({
  label,
  value,
  scales,
}: {
  label: string;
  value: unknown;
  scales: { gold: number; level: number };
}): React.JSX.Element {
  const row = object(value);
  const projections = Array.isArray(row.projections)
    ? row.projections.map(object)
    : [];
  if (value === null || typeof value !== "object")
    return (
      <section style={{ minWidth: 0 }}>
        <h4>{label}</h4>
        <p>Forecast unavailable</p>
      </section>
    );
  return (
    <section style={{ minWidth: 0 }}>
      <h4>{label}</h4>
      <p>
        {text(row.line_id)} · Expected placement {text(row.expected_placement)}{" "}
        ± {text(row.standard_error)}
      </p>
      <p>{describeSchedule(row.schedule)}</p>
      <p>
        Hit {percent(row.hit_probability) ?? "unavailable"} · death{" "}
        {percent(row.death_probability) ?? "unavailable"} · death placement
        cost {number(row.death_placement_cost)?.toFixed(2) ?? "unavailable"} ·
        confidence {percent(row.confidence) ?? "unavailable"}
      </p>
      <svg
        role="img"
        aria-label={`${label}: gold and level forecast`}
        viewBox="0 0 480 180"
        style={{ width: "100%", maxWidth: 640 }}
      >
        <title>{label}: gold and level forecast</title>
        <text x="12" y="16" fill="currentColor">
          Gold 0–{scales.gold} (solid) · Level 0–{scales.level} (dashed)
        </text>
        {projections.map((point, index) => (
          <text
            key={index}
            x={25 + (index * 420) / Math.max(1, projections.length - 1)}
            y="155"
            textAnchor={
              index === 0
                ? "start"
                : index === projections.length - 1
                  ? "end"
                  : "middle"
            }
            fill="currentColor"
            fontSize="12"
          >
            {text(point.round_id)}
          </text>
        ))}
        <line x1="20" y1="135" x2="460" y2="135" stroke="currentColor" />
        {(["gold", "level"] as const).map((field, series) => {
          const valid = projections
            .map((point, index) => ({ value: number(point[field]), index }))
            .filter((point) => point.value !== null);
          const maximum = scales[field];
          // Missing values break the curve rather than implying a measured value.
          return valid.map((point) => {
            const next = valid.find((other) => other.index === point.index + 1);
            const x = (index: number): number =>
              25 + (index * 420) / Math.max(1, projections.length - 1);
            const y = (value: number): number => 130 - (value / maximum) * 95;
            return (
              <g key={`${field}:${point.index}`}>
                {next ? (
                  <line
                    x1={x(point.index)}
                    y1={y(point.value!)}
                    x2={x(next.index)}
                    y2={y(next.value!)}
                    stroke={series ? "#a78bfa" : "#38bdf8"}
                    strokeDasharray={series ? "5 3" : undefined}
                    strokeWidth="2"
                  />
                ) : null}
                <circle
                  cx={x(point.index)}
                  cy={y(point.value!)}
                  r="3"
                  fill={series ? "#a78bfa" : "#38bdf8"}
                />
              </g>
            );
          });
        })}
      </svg>
      <table style={{ width: "100%", textAlign: "left" }}>
        <caption>{label} values</caption>
        <thead>
          <tr>
            <th>Round</th>
            <th>Gold</th>
            <th>Level</th>
            <th>HP</th>
          </tr>
        </thead>
        <tbody>
          {projections.map((point, index) => (
            <tr key={index}>
              <td>{text(point.round_id)}</td>
              <td>{text(point.gold)}</td>
              <td>{text(point.level)}</td>
              <td>{text(point.hp)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {projections.length === 0 ? <p>Forecast unavailable</p> : null}
    </section>
  );
}

const label = (value: unknown): string =>
  text(value).replaceAll("_", " ");
const optional = (value: unknown, prefix: string): string | null =>
  value === null || value === undefined ? null : `${prefix} ${text(value)}`;

const percent = (value: unknown): string | null => {
  const probability = number(value);
  return probability === null ? null : `${Math.round(probability * 100)}%`;
};

function PositioningRow({ row }: { row: RecordValue }): React.JSX.Element {
  const layout = Array.isArray(row.layout) ? row.layout.map(object) : [];
  return (
    <>
      <p>
        {text(row.action)} · Engine decision {text(row.engine_decision_id)} ·
        log {text(row.log_seq)} · confidence{" "}
        {percent(row.confidence) ?? "unavailable"}
      </p>
      {layout.length ? (
        <ul>
          {layout.map((unit, index) => (
            <li key={index}>
              {text(unit.unit_id)} → hex {text(unit.cell)}
            </li>
          ))}
        </ul>
      ) : (
        <p>No target layout recorded</p>
      )}
      <p>Layout {row.followed===true?'followed':row.followed===false?'not followed':'follow unknown'} · actual {label(row.result)} · forecast win {percent(row.win_probability)??'unavailable'}</p>
      <p>Shown status {label(object(row.shown).status)}</p>
      <p>Not costed · {label(row.reason)}</p>
    </>
  );
}

function TimelineRow({ row }: { row: RecordValue }): React.JSX.Element {
  const unavailable = object(row.unavailable);
  const shown = object(row.shown);
  const cost = number(row.cost);
  const uncertainty = number(row.paired_uncertainty);
  return (
    <>
      <p>
        {label(row.category)} · Engine decision {text(row.engine_decision_id)} ·
        log {text(row.log_seq)}
      </p>
      <p>
        {cost === null
          ? `${row.differed ? "Differed" : "Matched"} · no placement cost · ${label(unavailable.cost ?? "not recorded")}`
          : `Estimated signed cost ${cost.toFixed(2)} ± ${uncertainty === null ? "unavailable" : uncertainty.toFixed(2)}${row.close_call ? " · close call" : ""}`}
      </p>
      <p>
        Shown status {label(shown.status ?? "unavailable")}
        {shown.reason ? ` · ${label(shown.reason)}` : ""}
      </p>
      <p>Reason {label(row.reason)}</p>
    </>
  );
}

const gapRounds = (row: RecordValue): string => {
  const start = row.start_round_id, end = row.end_round_id;
  const known = (value: unknown): boolean => typeof value === "string" && value !== "";
  if (known(start) && known(end)) return `rounds ${text(start)} to ${text(end)}`;
  if (known(start)) return `after round ${text(start)}`;
  if (known(end)) return `before round ${text(end)}`;
  return "rounds unavailable";
};

/** A logged capture gap holds no reviewed decisions; it is not a decision row. */
function GapRow({ row }: { row: RecordValue }): React.JSX.Element {
  const count = number(row.unreviewed_snapshot_count) ?? 0;
  return (
    <>
      <p>
        From {row.start === null ? "unknown start" : text(row.start)} to{" "}
        {text(row.end)} · log {text(row.log_seq)} · {gapRounds(row)}
      </p>
      <p>
        Decisions inside this gap are not reviewed ·{" "}
        {count === 0
          ? "no captured snapshots inside"
          : `${count} captured snapshot${count === 1 ? "" : "s"} not evaluated`}
      </p>
    </>
  );
}

function FightRow({ row }: { row: RecordValue }): React.JSX.Element {
  const unavailable = object(row.unavailable);
  const win = percent(row.win_probability);
  const predicted = number(row.predicted_hp_loss);
  return (
    <>
      <p>
        Opponent {text(row.opponent_id)} · fight started log{" "}
        {text(row.start_log_seq)} · {text(row.start_at)}
      </p>
      <p>
        {win === null && predicted === null
          ? `Forecast unavailable · ${label(unavailable.forecast ?? "not recorded")}`
          : `Forecast · win ${win ?? "unavailable"} · predicted HP loss ${predicted ?? "unavailable"}`}
      </p>
      <p>
        Actual · {row.result === null ? "result unknown" : label(row.result)} ·
        HP lost {number(row.actual_hp_loss) ?? "unavailable"}
      </p>
    </>
  );
}

function PlanRow({ row }: { row: RecordValue }): React.JSX.Element {
  const candidates = Array.isArray(row.candidates)
    ? row.candidates.map(text)
    : [];
  const status = row.status === "committed" ? "Committed" : "Open";
  return (
    <>
      <p>
        {[
          status,
          optional(row.target, "target") ?? "no target",
          optional(row.backup, "backup"),
        ]
          .filter(Boolean)
          .join(" · ")}
      </p>
      <p>
        {candidates.length
          ? `Candidates ${candidates.join(", ")}`
          : "No candidate comps recorded"}
      </p>
      {row.pivot_to !== null && row.pivot_to !== undefined ? (
        <p>
          Pivot {text(row.pivot_from)} → {text(row.pivot_to)} at{" "}
          {text(row.pivot_round)}
        </p>
      ) : null}
      {row.rejected_target !== null && row.rejected_target !== undefined ? (
        <p>Rejected target {text(row.rejected_target)}</p>
      ) : null}
      <p>
        {[
          optional(row.player_label, "Player comp") ?? "Player comp unread",
          optional(row.divergence_round, "diverged"),
          optional(row.observed_lock, "locked"),
        ]
          .filter(Boolean)
          .join(" · ")}
      </p>
      <p>
        {row.called_status === "display_attribution_unavailable"
          ? "Called status unavailable · display attribution unavailable"
          : `Called status ${label(row.called_status)}`}
      </p>
    </>
  );
}

export function ReviewSection(props: ReviewSectionProps): React.JSX.Element {
  const fallbackScope = useRef({ request: props.request, serial: 0 });
  if (
    props.scopeKey === undefined &&
    fallbackScope.current.request !== props.request
  ) {
    fallbackScope.current = {
      request: props.request,
      serial: fallbackScope.current.serial + 1,
    };
  }
  return (
    <ScopedSection
      key={JSON.stringify([
        props.scopeKey ?? fallbackScope.current.serial,
        props.name,
        props.path,
      ])}
      {...props}
    />
  );
}

function ScopedSection({
  name,
  path,
  request,
  onDebug,
}: ReviewSectionProps): React.JSX.Element {
  const [state, setState] = useState<{
    rows: unknown[];
    next: number | null;
    error: string | null;
    loading: boolean;
  }>({ rows: [], next: null, error: null, loading: true });
  const [cursor, setCursor] = useState(0);
  const [retry, setRetry] = useState(0);
  const pathKey = JSON.stringify(path);
  const requestRef = useRef(request);
  requestRef.current = request;
  useEffect(() => {
    let active = true;
    setState((previous) => ({
      rows: cursor === 0 ? [] : previous.rows,
      next: null,
      error: null,
      loading: true,
    }));
    const selected: Path = JSON.parse(pathKey);
    if (!same(selected, ["surface", name])) {
      setState({
        rows: [],
        next: null,
        error: "Only typed review surfaces can be opened here",
        loading: false,
      });
      return;
    }
    void readRows(requestRef.current, selected, cursor)
      .then(({ rows, next }) => {
        if (active)
          setState((previous) => ({
            rows: cursor === 0 ? rows : [...previous.rows, ...rows],
            next,
            error: null,
            loading: false,
          }));
      })
      .catch((error) => {
        if (active)
          setState((previous) => ({
            ...previous,
            next: null,
            error:
              error instanceof Error
                ? error.message
                : "Review section unavailable",
            loading: false,
          }));
      });
    return () => {
      active = false;
    };
  }, [name, pathKey, cursor, retry]);
  if (state.loading && state.rows.length === 0)
    return <p role="status">Loading review section…</p>;
  return (
    <section aria-label={`${name.replaceAll("_", " ")} review`}>
      {state.error ? <p role="alert">{state.error}</p> : null}
      {state.rows.length === 0 && !state.error ? (
        <p>No records in this section</p>
      ) : null}
      {state.rows.map((value, index) => {
        const row = object(value),
          observed = object(row.observed);
        const forecasts = [row.recommended, row.actual].flatMap((value) => {
          const projections = object(value).projections;
          return Array.isArray(projections) ? projections.map(object) : [];
        });
        const scales = {
          gold: Math.max(
            1,
            ...forecasts.map((point) => number(point.gold) ?? 0),
          ),
          level: Math.max(
            1,
            ...forecasts.map((point) => number(point.level) ?? 0),
          ),
        };
        const debugPath = row.evidence_path;
        const gap = name === "timeline" && row.kind === "capture_gap";
        return (
          <article
            key={index}
            aria-label={
              gap
                ? `Capture gap · ${label(row.cause)} · ${gapRounds(row)}`
                : undefined
            }
            style={{
              marginBottom: 24,
              padding: 16,
              border: gap ? "2px dashed #f59e0b" : "1px solid #64748b",
              borderRadius: 8,
            }}
          >
            <h3>
              {gap
                ? `Capture gap · ${label(row.cause)}`
                : row.round_id === undefined
                  ? `Log ${text(row.log_seq)}`
                  : `Round ${text(row.round_id)}`}
            </h3>
            {gap ? (
              <GapRow row={row} />
            ) : name === "lines" ? (
              <>
                <p>
                  Observed · gold {text(observed.gold)} · level{" "}
                  {text(observed.level)} · HP {text(observed.hp)}
                </p>
                <p>
                  Forecasts start from this decision. Fitted player policy uses
                  the later observed schedule; it is an ex-post comparison.
                </p>
                <Forecast
                  label="Engine forecast"
                  value={row.recommended}
                  scales={scales}
                />
                <Forecast
                  label="Fitted player policy · ex-post"
                  value={row.actual}
                  scales={scales}
                />
                {row.pin === null || row.pin === undefined ? (
                  <p>No Line pinned at this decision</p>
                ) : (
                  <section>
                    <h4>
                      Pinned Line {text(object(row.pin).id)} ·{" "}
                      {describeSchedule(row.pin)}
                    </h4>
                    {row.pinned?<><Forecast label="Pinned forecast" value={row.pinned} scales={scales}/><p>Pinned estimated signed cost {number(row.pin_cost)?.toFixed(2)??'unavailable'}</p></>:<p>Pinned forecast unavailable · this review records the pinned schedule only</p>}
                  </section>
                )}
              </>
            ) : name === "positioning" ? (
              <PositioningRow row={row} />
            ) : name === "timeline" ? (
              <TimelineRow row={row} />
            ) : name === "fights" ? (
              <FightRow row={row} />
            ) : name === "plan_timeline" ? (
              <PlanRow row={row} />
            ) : (
              <dl>
                {Object.entries(row)
                  .filter(
                    ([key, item]) =>
                      key !== "evidence_path" &&
                      key !== "round_id" &&
                      (typeof item !== "object" || item === null),
                  )
                  .map(([key, item]) => (
                    <div key={key}>
                      <dt>{key.replaceAll("_", " ")}</dt>
                      <dd>{text(item)}</dd>
                    </div>
                  ))}
              </dl>
            )}
            {Object.entries(object(row.unavailable)).map(([key, reason]) => (
              <p key={key}>
                {key.replaceAll("_", " ")} unavailable: {text(reason)}
              </p>
            ))}
            {Array.isArray(debugPath) &&
            debugPath.every(
              (key) => typeof key === "string" || Number.isInteger(key),
            ) ? (
              <button type="button" onClick={() => onDebug(debugPath as Path)}>
                Debug evidence
              </button>
            ) : null}
          </article>
        );
      })}
      {state.error ? (
        <button type="button" onClick={() => setRetry((value) => value + 1)}>
          Retry load
        </button>
      ) : state.next !== null ? (
        <button
          type="button"
          disabled={state.loading}
          onClick={() => setCursor(state.next!)}
        >
          Load more
        </button>
      ) : null}
      {state.loading ? <p role="status">Loading more…</p> : null}
    </section>
  );
}
