import { contextBridge, ipcRenderer } from 'electron'
import type { SessionMode } from '../shared/protocol'
import type {EvidencePage,LiveSurfaceShown,LivePreviewShown,ReviewNoticeShown,PinLine,RequestEvidencePage,RequestReview,ReviewResponse,ReviewGames} from '../shared/messages'
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
  reviewNoticeShown: (message:Omit<ReviewNoticeShown,'v'|'type'>):void => ipcRenderer.send('review-notice-shown',message),
  livePreviewShown: (message:Omit<LivePreviewShown,'v'|'type'>):void => ipcRenderer.send('live-preview-shown',message),
  liveShown: (message:Omit<LiveSurfaceShown,'v'|'type'>):void => ipcRenderer.send('live-shown',message),
  pinLine: (message:Omit<PinLine,'v'|'type'>):void => ipcRenderer.send('pin-line',message),
  evidencePage: (message:Omit<RequestEvidencePage,'v'|'type'|'request_id'>):Promise<EvidencePage> => ipcRenderer.invoke('evidence-page',message),
  reviewGames:():Promise<ReviewGames>=>ipcRenderer.invoke('review-games'),
  requestReview:(message:Omit<RequestReview,'v'|'type'|'request_id'>):Promise<ReviewResponse>=>ipcRenderer.invoke('review-request',message),
  openReview:(gameId:string):void=>ipcRenderer.send('open-review',gameId),
  overlayInteractive: (interactive:boolean):void => ipcRenderer.send('overlay-interactive',interactive),
  setMode: (mode: SessionMode): void => ipcRenderer.send('set-mode', mode),
}

export type CoachApi = typeof coach

contextBridge.exposeInMainWorld('coach', coach)
