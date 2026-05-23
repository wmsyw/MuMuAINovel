import { expect, test } from '@playwright/test'

test('previews lorebook prompt trace in Prompt Workshop', async ({ page }) => {
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
  await page.route('**/api/prompt-workshop/status', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ mode: 'client', instance_id: 'e2e', cloud_connected: true }) })
  })
  await page.route('**/api/prompt-workshop/items**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: { total: 0, page: 1, limit: 12, items: [], categories: [] } }),
    })
  })
  await page.route('**/api/lorebook/projects/1/prompt-preview', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        project_id: '1',
        trace: {
          source_type: 'lorebook',
          selected_lore_ids: ['lore-order', 'lore-city'],
          total_candidates: 2,
          selected_count: 2,
          budget_estimate: { chars_used: 24, budget_chars: 24, estimated_tokens: 12, chars_per_token: 2 },
          items: [
            {
              order: 1,
              id: 'lore-order',
              title: '青岚阁',
              source_type: 'lorebook',
              entry_source_type: 'imported',
              priority: 30,
              matched_keys: ['青岚阁'],
              content: '青岚阁只在暴雨夜打开山门。',
              original_content_length: 13,
              selected_content_length: 13,
              trimmed: false,
            },
            {
              order: 2,
              id: 'lore-city',
              title: '龙城',
              source_type: 'lorebook',
              entry_source_type: 'manual',
              priority: 20,
              matched_keys: ['龙城'],
              content: '龙城建立在七层玄铁城…',
              original_content_length: 14,
              selected_content_length: 11,
              trimmed: true,
            },
          ],
          final_preview_text: '### 1. 青岚阁 [lore-order]\n来源: lorebook/imported\n匹配关键词: 青岚阁\n青岚阁只在暴雨夜打开山门。',
        },
      }),
    })
  })

  await page.goto('/project/1/prompt-workshop')
  await expect(page.getByRole('heading', { name: /提示词工坊/ })).toBeVisible()

  await page.getByRole('tab', { name: 'Lorebook预览' }).click()
  await page.getByPlaceholder(/粘贴章节大纲/).fill('青岚阁派人前往龙城。')
  await page.getByRole('button', { name: '生成预览' }).click()

  await expect(page.getByText('选中 ID：')).toBeVisible()
  await expect(page.getByText('lore-order').first()).toBeVisible()
  await expect(page.getByText('来源: lorebook/imported').first()).toBeVisible()
  await expect(page.getByText('青岚阁只在暴雨夜打开山门。').first()).toBeVisible()
})
