// @vitest-environment jsdom
import { act, createElement } from "react";
import { createRoot } from "react-dom/client";
import { expect, it } from "vitest";
import { ReviewSection } from "../src/renderer/src/review/ReviewSection";
Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true });
const projection = { round_id: "3-3", gold: 42, level: 6, hp: 59 };
const row = {
  round_id: "3-2",
  observed: { gold: 35, level: 5, hp: 60 },
  recommended: {
    line_id: "guide:A",
    expected_placement: 3.1,
    standard_error: 0.2,
    projections: [projection],
  },
  actual: {
    line_id: "fitted-hold",
    expected_placement: 4.2,
    standard_error: 0.3,
    projections: [{ ...projection, gold: 50, hp: 40 }],
  },
  evidence_path: ["lines", 0],
};
const paths: unknown[] = [];
const request = async (
  _operation: string,
  args: Record<string, unknown>,
): Promise<Record<string, unknown>> => {
  paths.push(args.path);
  const path = args.path as (string | number)[];
  let value: unknown = { surface: { lines: [row] } };
  for (const key of path)
    value = (value as Record<string | number, unknown>)[key];
  return {
    kind: Array.isArray(value) ? "array" : "object",
    path,
    items: Object.entries(value as object).map(([key, child]) => ({
      path: [...path, Array.isArray(value) ? Number(key) : key],
      ...(typeof child === "object" && child !== null
        ? { reference: true }
        : { value: child }),
    })),
    next_cursor: null,
  };
};
it("shows protected Line forecasts separately from observed outcomes and opens only explicit Debug evidence", async () => {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  const debug: unknown[] = [];
  try {
    await act(async () =>
      root.render(
        createElement(ReviewSection, {
          name: "lines",
          path: ["surface", "lines"],
          request,
          onDebug: (path) => debug.push(path),
        }),
      ),
    );
    expect(host.textContent).toContain("Engine forecast");
    expect(host.textContent).toContain("Fitted player policy · ex-post");
    expect(host.textContent).toContain("Observed · gold 35");
    expect(host.textContent).toContain("guide:A");
    expect(host.textContent).toContain("59");
    expect(host.querySelectorAll("svg")).toHaveLength(2);
    expect(host.querySelector("pre")).toBeNull();
    expect(paths.every((path) => (path as string[])[0] === "surface")).toBe(
      true,
    );
    act(() => (host.querySelector("button") as HTMLButtonElement).click());
    expect(debug).toEqual([["lines", 0]]);
  } finally {
    act(() => root.unmount());
    host.remove();
  }
});
it("keeps long sections usable by loading the next protected page on demand", async () => {
  const host = document.createElement("div");
  const root = createRoot(host);
  const pagedRequest = async (
    _operation: string,
    args: Record<string, unknown>,
  ): Promise<Record<string, unknown>> => {
    const cursor = args.cursor as number;
    return {
      path: args.path,
      kind: "array",
      items: [
        {
          path: ["surface", "lines", cursor],
          value: { ...row, round_id: cursor === 0 ? "3-2" : "4-1" },
        },
      ],
      next_cursor: cursor === 0 ? 1 : null,
    };
  };
  try {
    await act(async () =>
      root.render(
        createElement(ReviewSection, {
          name: "lines",
          path: ["surface", "lines"],
          request: pagedRequest,
          onDebug: () => {},
        }),
      ),
    );
    expect(host.textContent).toContain("Round 3-2");
    expect(host.textContent).not.toContain("Round 4-1");
    const more = [...host.querySelectorAll("button")].find(
      (button) => button.textContent === "Load more",
    )!;
    expect(more).toBeDefined();
    await act(async () => more.click());
    expect(host.textContent).toContain("Round 4-1");
    expect(host.textContent).toContain("Round 3-2");
    expect(
      [...host.querySelectorAll("button")].some(
        (button) => button.textContent === "Load more",
      ),
    ).toBe(false);
    const fights = async (
      _operation: string,
      args: Record<string, unknown>,
    ): Promise<Record<string, unknown>> => ({
      path: args.path,
      kind: "array",
      items:
        args.cursor === 0
          ? [
              {
                path: ["surface", "fights", 0],
                value: { round_id: "5-1", result: "win" },
              },
            ]
          : [],
      next_cursor: null,
    });
    await act(async () =>
      root.render(
        createElement(ReviewSection, {
          name: "fights",
          path: ["surface", "fights"],
          request: fights,
          onDebug: () => {},
        }),
      ),
    );
    expect(host.textContent).toContain("Round 5-1");
    expect(host.textContent).not.toContain("Round 3-2");
  } finally {
    act(() => root.unmount());
  }
});
it("discards an old report response after the selected protected section changes", async () => {
  const host = document.createElement("div");
  const root = createRoot(host);
  let release: (value: Record<string, unknown>) => void = () => {};
  const delayed = async (): Promise<Record<string, unknown>> =>
    new Promise((resolve) => {
      release = resolve;
    });
  const current = async (
    _operation: string,
    args: Record<string, unknown>,
  ): Promise<Record<string, unknown>> => ({
    path: args.path,
    kind: "array",
    items: [
      {
        path: ["surface", "fights", 0],
        value: { round_id: "5-1", result: "win", actual_hp_loss: 0 },
      },
    ],
    next_cursor: null,
  });
  try {
    await act(async () =>
      root.render(
        createElement(ReviewSection, {
          name: "lines",
          path: ["surface", "lines"],
          request: delayed,
          onDebug: () => {},
        }),
      ),
    );
    await act(async () =>
      root.render(
        createElement(ReviewSection, {
          name: "fights",
          path: ["surface", "fights"],
          request: current,
          onDebug: () => {},
        }),
      ),
    );
    await act(async () =>
      release({
        path: ["surface", "lines"],
        kind: "array",
        items: [{ path: ["surface", "lines", 0], value: row }],
        next_cursor: null,
      }),
    );
    expect(host.textContent).toContain("Round 5-1");
    expect(host.textContent).not.toContain("guide:A");
  } finally {
    act(() => root.unmount());
  }
});
