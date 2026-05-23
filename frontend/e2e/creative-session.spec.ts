import { expect, test } from '@playwright/test'

type SessionRecord = {
  id: string
  project_id: string
  user_id: string
  title: string
  status: string
  metadata: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

type MessageRecord = {
  id: string
  session_id: string
  project_id: string
  user_id: string
  role: string
  content: string
  position: number
  metadata: Record<string, unknown> | null
  created_at: string
}

test('creates, resumes, and searches a creative session', async ({ page }) => {
  const now = new Date('2026-05-22T12:00:00.000Z').toISOString()
  const sessions: SessionRecord[] = []
  const messagesBySession = new Map<string, MessageRecord[]>()

  await page.route('**/api/auth/user', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        user_id: 'user-e2e',
        username: 'e2e',
        display_name: 'E2E作者',
        trust_level: 1,
        is_admin: false,
        linuxdo_id: 'linuxdo-e2e',
        created_at: now,
        last_login: now,
      }),
    })
  })

  await page.route('**/api/projects/1', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: '1',
        title: 'E2E Novel',
        description: 'stub project',
        theme: 'storm',
        genre: 'fantasy',
        target_words: 100000,
        current_words: 0,
        status: 'planning',
        wizard_status: 'completed',
        outline_mode: 'one-to-many',
        created_at: now,
        updated_at: now,
      }),
    })
  })

  await page.route('**/api/outlines/project/1', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ total: 0, items: [] }) })
  })
  await page.route('**/api/characters/project/1**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ total: 0, items: [] }) })
  })
  await page.route('**/api/chapters/project/1', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ total: 0, items: [] }) })
  })
  await page.route('**/api/tasks?**', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [] }) })
  })

  await page.route('**/api/creative-sessions/projects/1/search**', async (route) => {
    const url = new URL(route.request().url())
    const query = url.searchParams.get('query') || ''
    const items = sessions.flatMap((session) => {
      const messages = messagesBySession.get(session.id) || []
      return messages
        .filter((message) => message.content.includes(query))
        .map((message) => ({
          session_id: session.id,
          session_title: session.title,
          message_id: message.id,
          project_id: message.project_id,
          user_id: message.user_id,
          role: message.role,
          content: message.content,
          position: message.position,
          created_at: message.created_at,
        }))
    })

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ query, total: items.length, items }),
    })
  })

  await page.route('**/api/creative-sessions/projects/1', async (route) => {
    if (route.request().method() === 'POST') {
      const body = JSON.parse(route.request().postData() || '{}') as { title?: string }
      const session: SessionRecord = {
        id: `session-${sessions.length + 1}`,
        project_id: '1',
        user_id: 'user-e2e',
        title: body.title || '未命名创作会话',
        status: 'active',
        metadata: null,
        created_at: now,
        updated_at: now,
      }
      sessions.unshift(session)
      messagesBySession.set(session.id, [])
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(session) })
      return
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ total: sessions.length, items: sessions }),
    })
  })

  await page.route('**/api/creative-sessions/*/messages', async (route) => {
    const sessionId = route.request().url().match(/creative-sessions\/([^/]+)\/messages/)?.[1] || ''
    const body = JSON.parse(route.request().postData() || '{}') as { role?: string; content: string }
    const existing = messagesBySession.get(sessionId) || []
    const session = sessions.find(item => item.id === sessionId)
    const record: MessageRecord = {
      id: `message-${existing.length + 1}`,
      session_id: sessionId,
      project_id: '1',
      user_id: 'user-e2e',
      role: body.role || 'note',
      content: body.content,
      position: existing.length,
      metadata: null,
      created_at: now,
    }
    existing.push(record)
    messagesBySession.set(sessionId, existing)
    if (session) session.updated_at = now
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(record) })
  })

  await page.route('**/api/creative-sessions/*', async (route) => {
    const sessionId = route.request().url().match(/creative-sessions\/([^/?]+)/)?.[1] || ''
    const session = sessions.find(item => item.id === sessionId)
    if (!session) {
      await route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: '创作会话不存在' }) })
      return
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ...session, messages: messagesBySession.get(session.id) || [] }),
    })
  })

  await page.goto('/project/1/creative-sessions')
  await expect(page.getByRole('heading', { name: '创作会话' })).toBeVisible()

  await page.getByLabel('会话标题').fill('E2E Draft Room')
  await page.getByRole('button', { name: '创建' }).click()
  await expect(page.getByText('会话记录：E2E Draft Room')).toBeVisible()

  await page.getByLabel('创作记录内容').fill('Brainstorm a storm-lit opening scene.')
  await page.getByRole('button', { name: '写入' }).click()
  await expect(page.getByText('Brainstorm a storm-lit opening scene.')).toBeVisible()

  await page.reload()
  await expect(page.getByText('Brainstorm a storm-lit opening scene.')).toBeVisible()

  await page.getByLabel('检索关键词').fill('storm-lit')
  await page.getByRole('button', { name: '搜索' }).click()
  await expect(page.getByTestId('creative-session-search-results').getByText('E2E Draft Room')).toBeVisible()
})
