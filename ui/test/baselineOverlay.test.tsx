import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { expect, it } from 'vitest'
import { BaselineOverlay } from '../src/renderer/src/BaselineOverlay'
import type { ShellState } from '../src/shared/state'

it('anchored Baseline overlay shows only Guide highlight and numeric par, and vanishes in silent mode', () => {
  const state: ShellState = {
    core: 'running',
    mode: 'baseline',
    availableModes: ['silent', 'baseline'],
    gameflow: { clientRunning: true, phase: 'InProgress' },
    baseline: {
      v: 1,
      type: 'baseline_state',
      mode: 'baseline',
      status: 'Capture OK',
      stale: [],
      voice: null,
      content: {
        patch: 'fixture',
        snapshot_id: 'fixture',
        round_id: '3-2',
        guides: [],
        selected: null,
        xp_hint: null,
        par: { probability: 0.54, paused: null, uncertain: false },
        shop: [
          {
            slot: 1,
            entity: { id: 'fixture', name: 'Fixture carry', icon: '', cost: 3 },
            in_guide: true,
          },
        ],
        recipes: [],
        augments: [],
        wisps: [],
        faced: [],
        warnings: [],
        overlay_bounds: { x: 0, y: 0, width: 1280, height: 720 },
        overlay_allowed: true,
        phase: 'planning',
        anchors: [
          { kind: 'shop', index: 1, x: 0.2, y: 0.8, width: 0.1, height: 0.04 },
          { kind: 'par', index: 0, x: 0.4, y: 0.1, width: 0.15, height: 0.04 },
        ],
      },
    },
  }
  const html = renderToStaticMarkup(createElement(BaselineOverlay, { state }))
  expect(html).toContain('In Guide')
  expect(html).toContain('54%')
  expect(html).not.toContain('Buy')
  expect(
    renderToStaticMarkup(
      createElement(BaselineOverlay, { state: { ...state, mode: 'silent' } }),
    ),
  ).toBe('')
})
