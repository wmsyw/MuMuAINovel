import { expect, test } from '@playwright/test'

test('shows a controlled state for a missing creative-session project', async ({ page }) => {
  const now = new Date('2026-05-22T12:00:00.000Z').toISOString()

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

  await page.route('**/api/projects/404', async (route) => {
    await route.fulfill({
      status: 404,
      contentType: 'application/json',
      body: JSON.stringify({ detail: '项目不存在' }),
    })
  })

  await page.route('**/api/creative-sessions/**', async (route) => {
    await route.fulfill({
      status: 404,
      contentType: 'application/json',
      body: JSON.stringify({ detail: '创作会话不存在' }),
    })
  })

  await page.goto('/project/404/creative-sessions')

  await expect(page.getByText('项目不可用', { exact: true })).toBeVisible()
  await expect(page.getByText('Brainstorm a storm-lit opening scene.')).toHaveCount(0)
})
