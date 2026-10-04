import type { CoachApi } from './index'

declare global {
  interface Window {
    coach: CoachApi
  }
}
