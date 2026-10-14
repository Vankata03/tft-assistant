import { useEffect, useState } from "react";

type Path = (string | number)[];
type RecordValue = Record<string, unknown>;
export interface ReviewSectionProps {
  name: string;
  /** Change this when the authenticated report or mode epoch changes. Keep request stable within that scope. */
  scopeKey?: string;
  path: Path;
  request: (operation: string, args: RecordValue) => Promise<RecordValue>;
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
  "unavailable",
  "evidence_path",
  "line_id",
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
  "result",
  "actual_hp_loss",
  "win_probability",
  "predicted_hp_loss",
  "opponent_warning",
  "winner_unit_count",
  "winner_unit_count_source",
  "moment_id",
  "category",
  "cost",
  "paired_uncertainty",
  "close_call",
  "differed",
  "shown",
  "reason",
  "action",
]);
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
        if (kind === "value") return item.value;
        throw new Error("Long review strings require Debug");
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
        !["observed", "unavailable"].includes(String(path.at(-1)))
      )
        continue;
      const value =
        item.reference === true
          ? await readMember(request, member as Path, budget, depth + 1)
          : item.value;
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
        : item.value,
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
}: {
  label: string;
  value: unknown;
}): React.JSX.Element {
  const row = object(value);
  const projections = Array.isArray(row.projections)
    ? row.projections.map(object)
    : [];
  return (
    <section style={{ minWidth: 0 }}>
      <h4>{label}</h4>
      <p>
        {text(row.line_id)} · Expected placement {text(row.expected_placement)}{" "}
        ± {text(row.standard_error)}
      </p>
      <svg
        role="img"
        aria-label={`${label}: gold and level forecast`}
        viewBox="0 0 480 160"
        style={{ width: "100%", maxWidth: 640 }}
      >
        <title>{label}: gold and level forecast</title>
        <text x="12" y="16" fill="currentColor">
          Gold (solid) · level (dashed), separate scales
        </text>
        <line x1="20" y1="135" x2="460" y2="135" stroke="currentColor" />
        {(["gold", "level"] as const).map((field, series) => {
          const valid = projections
            .map((point, index) => ({ value: number(point[field]), index }))
            .filter((point) => point.value !== null);
          const maximum = Math.max(1, ...valid.map((point) => point.value!));
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

export function ReviewSection(props: ReviewSectionProps): React.JSX.Element {
  return (
    <ScopedSection
      key={JSON.stringify([props.scopeKey ?? null, props.name, props.path])}
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
  const pathKey = JSON.stringify(path);
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
    void readRows(request, selected, cursor)
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
  }, [name, pathKey, request, cursor]);
  if (state.loading && state.rows.length === 0)
    return <p role="status">Loading review section…</p>;
  if (state.error) return <p role="alert">{state.error}</p>;
  return (
    <section aria-label={`${name.replaceAll("_", " ")} review`}>
      {state.rows.length === 0 ? <p>No records in this section</p> : null}
      {state.rows.map((value, index) => {
        const row = object(value),
          observed = object(row.observed);
        const debugPath = row.evidence_path;
        return (
          <article
            key={index}
            style={{
              marginBottom: 24,
              padding: 16,
              border: "1px solid #64748b",
              borderRadius: 8,
            }}
          >
            <h3>Round {text(row.round_id)}</h3>
            {name === "lines" ? (
              <>
                <p>
                  Observed · gold {text(observed.gold)} · level{" "}
                  {text(observed.level)} · HP {text(observed.hp)}
                </p>
                <p>
                  Forecasts start from this decision. Fitted player policy uses
                  the later observed schedule; it is an ex-post comparison.
                </p>
                <Forecast label="Engine forecast" value={row.recommended} />
                <Forecast
                  label="Fitted player policy · ex-post"
                  value={row.actual}
                />
              </>
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
      {state.next !== null ? (
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
