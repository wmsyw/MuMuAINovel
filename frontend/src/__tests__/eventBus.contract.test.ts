import { afterEach, describe, expect, it, vi } from 'vitest'

import { EventNames, eventBus } from '../store/eventBus'

afterEach(() => {
  eventBus.removeAllListeners()
})

describe('eventBus contract', () => {
  it('delivers typed project refresh payloads to registered listeners', () => {
    const listener = vi.fn()
    const payload = { projectId: 'project-001', reason: 'fixture-refresh' }

    eventBus.on(EventNames.PROJECT_NEEDS_REFRESH, listener)
    eventBus.emit(EventNames.PROJECT_NEEDS_REFRESH, payload)

    expect(listener).toHaveBeenCalledTimes(1)
    expect(listener).toHaveBeenCalledWith(payload)
    expect(eventBus.listenerCount(EventNames.PROJECT_NEEDS_REFRESH)).toBe(1)
  })

  it('supports one-time listeners and listener removal', () => {
    const onceListener = vi.fn()
    const persistentListener = vi.fn()

    eventBus.on(EventNames.CHAPTER_NEEDS_REFRESH, persistentListener)
    eventBus.once(EventNames.CHAPTER_NEEDS_REFRESH, onceListener)

    eventBus.emit(EventNames.CHAPTER_NEEDS_REFRESH, { chapterId: 'chapter-001' })
    eventBus.emit(EventNames.CHAPTER_NEEDS_REFRESH, { chapterId: 'chapter-002' })
    eventBus.off(EventNames.CHAPTER_NEEDS_REFRESH, persistentListener)

    expect(onceListener).toHaveBeenCalledTimes(1)
    expect(persistentListener).toHaveBeenCalledTimes(2)
    expect(eventBus.listenerCount(EventNames.CHAPTER_NEEDS_REFRESH)).toBe(0)
  })
})
