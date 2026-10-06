import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { expect, it } from 'vitest'
import { SessionModeSelector } from '../src/renderer/src/App'
import type { ShellState } from '../src/shared/state'

it('public build mode selector hides unavailable Live mode', () => {
  const state: ShellState = {
    core: 'running', gameflow: { clientRunning: true, phase: 'Lobby' }, mode: 'baseline',
    availableModes: ['silent', 'baseline'],
  }
  const html = renderToStaticMarkup(createElement(SessionModeSelector, { state, onChange: () => {} }))
  expect(html).toContain('value="silent"')
  expect(html).toContain('value="baseline"')
  expect(html).not.toContain('value="live"')
})
