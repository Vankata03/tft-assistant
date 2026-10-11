import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { expect, it } from 'vitest'
import { Cockpit } from '../src/renderer/src/Cockpit'
import type { ShellState } from '../src/shared/state'

it('silent cockpit suppresses stale game content and renders only status', () => {
  const state: ShellState = {
    core: 'running',
    gameflow: { clientRunning: true, phase: 'InProgress' },
    mode: 'silent',
    availableModes: ['silent', 'baseline'],
    baseline: {
      v: 1,
      type: 'baseline_state',
      mode: 'baseline',
      status: 'Capture OK',
      stale: [],
      voice: null,
      content: {
        patch: 'secret-patch',
        snapshot_id: 'secret',
        round_id: '3-2',
        guides: [],
        selected: null,
        xp_hint: null,
        par: { probability: 0.5, paused: null, uncertain: false },
        shop: [],
        recipes: [],
        augments: [],
        wisps: [],
        faced: [],
        warnings: [],
        phase: 'planning',
        anchors: [],
        overlay_bounds: null,
        overlay_allowed: false,
      },
    },
  }
  const html = renderToStaticMarkup(
    createElement(Cockpit, {
      state,
      onSelectGuide: () => {},
      onMode: () => {},
    }),
  )
  expect(html).toContain('Silent game')
  expect(html).not.toContain('secret')
  expect(html).not.toContain('Par win chance')
  expect(html).not.toContain('Guides')
})

it('Baseline renders Guide picker, static content and a number-only par chip together', () => {
  const unit = { id: 'fixture-unit', name: 'Fixture carry', icon: '', cost: 3 }
  const guide = {
    id: 'guide-a',
    name: 'Guide A',
    tier: 'S',
    units: [unit],
    early_layout: [{ entity: unit, position: null }],
    final_layout: [{ entity: unit, position: 7 }],
    stage_tips: { '3': 'Fixture stage plan' },
    stage_plan: [],
    carousel: [unit],
    alternatives: [],
  }
  const state: ShellState = {
    core: 'running',
    mode: 'baseline',
    gameflow: { clientRunning: true, phase: 'InProgress' },
    availableModes: ['silent', 'baseline'],
    baseline: {
      v: 1,
      type: 'baseline_state',
      mode: 'baseline',
      status: 'Capture OK',
      stale: [],
      voice: null,
      content: {
        patch: 'fixture-patch',
        snapshot_id: 'fixture',
        round_id: '3-2',
        guides: [guide],
        selected: guide,
        xp_hint: {
          target_level: 7,
          target_round: '3-4',
          buys: 2,
          gold: 8,
          passive_xp: 4,
          text: 'Guide: 7 at 3-4 · 2 XP buys (8 gold) short',
        },
        par: { probability: 0.54, paused: null, uncertain: false },
        shop: [],
        recipes: [],
        augments: [
          {
            entity: { ...unit, id: 'tier-a', name: 'Fixture A augment' },
            tier: 'A',
            global_tier: 'A',
            in_guide: false,
            offered: false,
            offer_index: null,
          },
          {
            entity: { ...unit, id: 'tier-s', name: 'Fixture S augment' },
            tier: 'S',
            global_tier: 'S',
            in_guide: false,
            offered: false,
            offer_index: null,
          },
        ],
        wisps: [],
        faced: [{ name: 'Fixture rival', result: 'win' }],
        warnings: [],
        phase: 'planning',
        anchors: [],
        overlay_bounds: null,
        overlay_allowed: false,
      },
    },
  }
  const html = renderToStaticMarkup(
    createElement(Cockpit, {
      state,
      onSelectGuide: () => {},
      onMode: () => {},
    }),
  )
  for (const text of [
    'Guides',
    'Early layout',
    'Final layout',
    'Carousel priorities',
    '54%',
    'Fixture rival',
    '2 XP buys',
    'Unplaced',
  ])
    expect(html).toContain(text)
  expect(html).not.toContain('Level now')
  expect(html.indexOf('Fixture S augment')).toBeLessThan(
    html.indexOf('Fixture A augment'),
  )
})

it('stage Wisp labels render as static references, preserve unavailable rows and disappear in silent mode', async () => {
  const { BaselineOverlay } = await import('../src/renderer/src/BaselineOverlay')
  const content = {
    patch: 'fixture', snapshot_id: 'fixture', round_id: '3-2', guides: [], selected: null,
    xp_hint: null, par: { probability: null, paused: 'unread', uncertain: false },
    shop: [], recipes: [], augments: [], faced: [], warnings: [], phase: 'planning',
    anchors: [{ kind: 'wisp', index: 4, x: .8, y: .8, width: .15, height: .05 }],
    overlay_bounds: { x: 0, y: 0, width: 1280, height: 720 }, overlay_allowed: true,
    wisps: [{ entity: { id: 'wisp', name: 'Fixture Wisp', icon: '', cost: 0 }, worth: .12,
      worth_label: 'situational', worth_stage: '3', paired_standard_error: .03, source: 'owner', offered_slot: 4 }],
  } as NonNullable<NonNullable<ShellState['baseline']>['content']>
  const state: ShellState = {
    core: 'running', mode: 'baseline', availableModes: ['silent', 'baseline'],
    gameflow: { clientRunning: true, phase: 'InProgress' },
    baseline: { v: 1, type: 'baseline_state', mode: 'baseline', status: 'Capture OK', stale: [], voice: null, content },
  }
  const cockpit = renderToStaticMarkup(createElement(Cockpit, { state, onSelectGuide: () => {}, onMode: () => {} }))
  expect(cockpit).toContain('Stage 3 · Situational')
  const overlay = renderToStaticMarkup(createElement(BaselineOverlay, { state }))
  expect(overlay).toContain('Static worth Stage 3 · Situational')
  expect(overlay).not.toContain('Buy')
  const unavailable = { ...state, baseline: { ...state.baseline!, content: { ...content,
    wisps: [{ ...content.wisps[0]!, worth: null, worth_label: null, paired_standard_error: null }] } } }
  expect(renderToStaticMarkup(createElement(BaselineOverlay, { state: unavailable }))).toContain('static Wisp worth unavailable')
  expect(renderToStaticMarkup(createElement(BaselineOverlay, { state: { ...state, mode: 'silent' } }))).toBe('')
})
