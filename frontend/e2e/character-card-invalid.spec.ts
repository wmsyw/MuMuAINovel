import { expect, test, type Page, type Route } from '@playwright/test'

type CharacterRecord = {
  id: string
  project_id: string
  name: string
  role_type?: string
  writing_notes?: string
  speech_patterns?: string
  motivations?: string
  arc_summary?: string
  card_version?: number
  created_at: string
  updated_at: string
}

const now = new Date('2026-05-22T12:00:00.000Z').toISOString()

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
}

async function stubCharacterShell(page: Page, characters: CharacterRecord[]) {
  await page.route('**/api/auth/user', route => fulfillJson(route, {
    user_id: 'user-e2e',
    username: 'e2e',
    display_name: 'E2E作者',
    trust_level: 1,
    is_admin: false,
    linuxdo_id: 'linuxdo-e2e',
    created_at: now,
    last_login: now,
  }))
  await page.route('**/api/projects/1', route => fulfillJson(route, {
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
  }))
  await page.route('**/api/outlines/project/1', route => fulfillJson(route, { total: 0, items: [] }))
  await page.route('**/api/chapters/project/1', route => fulfillJson(route, { total: 0, items: [] }))
  await page.route('**/api/tasks?**', route => fulfillJson(route, { items: [] }))
  await page.route('**/api/careers**', route => fulfillJson(route, { total: 0, main_careers: [], sub_careers: [] }))
  await page.route('**/api/settings', route => fulfillJson(route, { allow_ai_entity_generation: false }))
  await page.route('**/api/extraction/candidates**', route => fulfillJson(route, { total: 0, items: [] }))
  await page.route('**/api/timeline/projects/1/state**', route => fulfillJson(route, {
    project_id: '1',
    point: { chapter_id: null, chapter_number: 0, chapter_order: 0 },
    relationships: [],
    affiliations: [],
    professions: [],
  }))
  await page.route('**/api/timeline/projects/1/history**', route => fulfillJson(route, { total: 0, items: [] }))
  await page.route('**/api/characters/project/1**', route => fulfillJson(route, { total: characters.length, items: characters }))
}

test('shows controlled validation feedback for malformed character-card import', async ({ page }) => {
  const characters: CharacterRecord[] = [{
    id: 'character-existing',
    project_id: '1',
    name: '顾青',
    role_type: 'supporting',
    writing_notes: '原有备注不可被错误导入覆盖',
    speech_patterns: '平稳陈述',
    motivations: '守护家族藏书',
    arc_summary: '维持守护者身份',
    card_version: 1,
    created_at: now,
    updated_at: now,
  }]
  let importCalled = false

  await stubCharacterShell(page, characters)
  await page.route('**/api/characters/validate-import', route => fulfillJson(route, {
    valid: false,
    version: 'unknown',
    statistics: { characters: 0, organizations: 0 },
    errors: ['JSON格式无效，无法读取角色卡片', 'card_version 必须大于等于 1'],
    warnings: [],
  }))
  await page.route('**/api/characters/import?project_id=1', async (route) => {
    importCalled = true
    await fulfillJson(route, { detail: '不应执行导入' }, 500)
  })

  await page.goto('/project/1/characters')
  const existingCard = page.locator('.ant-card').filter({ hasText: '顾青' })
  await expect(existingCard).toContainText('原有备注不可被错误导入覆盖')

  await page.getByRole('button', { name: '导入' }).click()
  await page.locator('input[type=file]').setInputFiles({
    name: 'broken-character-card.json',
    mimeType: 'application/json',
    buffer: Buffer.from('{broken json'),
  })

  await expect(page.locator('.ant-modal-confirm-title').filter({ hasText: '文件验证失败' })).toBeVisible()
  await expect(page.getByText('JSON格式无效，无法读取角色卡片')).toBeVisible()
  await expect(page.getByText('card_version 必须大于等于 1')).toBeVisible()
  expect(importCalled).toBe(false)
  expect(characters).toHaveLength(1)
  await expect(existingCard).toContainText('原有备注不可被错误导入覆盖')
  await expect(page.getByText('错误导入角色')).toHaveCount(0)
})
