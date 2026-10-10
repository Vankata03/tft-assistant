import { contextBridge, ipcRenderer } from 'electron'
import type { SessionMode } from '../shared/protocol'
import type { ShellState } from '../shared/state'

const coach = {
  getState: (): Promise<ShellState> => ipcRenderer.invoke('get-state'),
  onState: (listener: (state: ShellState) => void): (() => void) => {
    const handler = (_event: unknown, state: ShellState): void =>
      listener(state)
    ipcRenderer.on('state', handler)
    return () => ipcRenderer.removeListener('state', handler)
  },
  reportShown: (
    surface: 'cockpit' | 'overlay' | 'voice',
    contentId: string,
    timestamp: string,
  ): void => ipcRenderer.send('surface-shown', surface, contentId, timestamp),
  selectGuide: (guideId: string): void =>
    ipcRenderer.send('select-guide', guideId),
  setMode: (mode: SessionMode): void => ipcRenderer.send('set-mode', mode),
}

export type CoachApi = typeof coach

contextBridge.exposeInMainWorld('coach', coach)
