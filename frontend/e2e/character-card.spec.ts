import { expect, test, type Page, type Route } from '@playwright/test'

type CharacterRecord = {
  id: string
  project_id: string
  name: string
  age?: string
  gender?: string
  role_type?: string
  personality?: string
  appearance?: string
  background?: string
  relationships?: string
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

test('creates, edits, exports, imports, and displays native character-card fields', async ({ page }) => {
  const characters: CharacterRecord[] = []
  let createdPayload: Partial<CharacterRecord> | undefined
  let updatedPayload: Partial<CharacterRecord> | undefined
  let exportedPayload: unknown

  await stubCharacterShell(page, characters)

  await page.route('**/api/characters', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.fallback()
      return
    }

    createdPayload = JSON.parse(route.request().postData() || '{}') as Partial<CharacterRecord>
    const character: CharacterRecord = {
      id: 'character-created',
      project_id: '1',
      name: createdPayload.name || '未命名角色',
      role_type: createdPayload.role_type || 'supporting',
      age: createdPayload.age,
      gender: createdPayload.gender,
      personality: createdPayload.personality,
      appearance: createdPayload.appearance,
      background: createdPayload.background,
      writing_notes: createdPayload.writing_notes,
      speech_patterns: createdPayload.speech_patterns,
      motivations: createdPayload.motivations,
      arc_summary: createdPayload.arc_summary,
      card_version: createdPayload.card_version || 1,
      created_at: now,
      updated_at: now,
    }
    characters.push(character)
    await fulfillJson(route, character)
  })

  await page.route('**/api/characters/character-created', async (route) => {
    if (route.request().method() !== 'PUT') {
      await fulfillJson(route, characters[0])
      return
    }

    updatedPayload = JSON.parse(route.request().postData() || '{}') as Partial<CharacterRecord>
    characters[0] = { ...characters[0], ...updatedPayload, updated_at: now }
    await fulfillJson(route, characters[0])
  })

  await page.route('**/api/characters/export', async (route) => {
    const body = JSON.parse(route.request().postData() || '{}') as { character_ids: string[] }
    const exportedCharacters = characters.filter(character => body.character_ids.includes(character.id))
    exportedPayload = { version: '1.0', characters: exportedCharacters, organizations: [] }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: { 'content-disposition': 'attachment; filename=characters_export.json' },
      body: JSON.stringify(exportedPayload),
    })
  })

  await page.route('**/api/characters/validate-import', route => fulfillJson(route, {
    valid: true,
    version: '1.0',
    statistics: { characters: 1, organizations: 0 },
    errors: [],
    warnings: [],
  }))

  await page.route('**/api/characters/import?project_id=1', async (route) => {
    const imported: CharacterRecord = {
      id: 'character-imported',
      project_id: '1',
      name: '沈砚',
      role_type: 'supporting',
      writing_notes: '导入后保留的伏笔备注',
      speech_patterns: '短句收束，少用感叹',
      motivations: '寻找失踪的师父',
      arc_summary: '从旁观者成长为主动破局者',
      card_version: 3,
      created_at: now,
      updated_at: now,
    }
    characters.push(imported)
    await fulfillJson(route, {
      success: true,
      message: '导入成功',
      statistics: { total: 1, imported: 1, skipped: 0, errors: 0 },
      details: { imported_characters: ['沈砚'], imported_organizations: [], skipped: [], errors: [] },
      warnings: [],
    })
  })

  await page.goto('/project/1/characters')
  await expect(page.getByRole('heading', { name: '角色与组织管理' })).toBeVisible()

  await page.getByRole('button', { name: '创建角色' }).click()
  await page.getByLabel('角色名称').fill('林澜')
  await page.getByLabel('性格特点').fill('冷静、谨慎')
  await page.getByLabel('写作备注').fill('第一卷第八章埋下家族线索')
  await page.getByLabel('说话习惯').fill('称呼他人全名，句尾常停顿')
  await page.getByLabel('核心动机').fill('守住边城并查清旧案')
  await page.getByLabel('人物弧光').fill('从被动守城到主动揭露真相')
  await page.getByRole('spinbutton', { name: '卡片版本' }).fill('2')
  await page.getByRole('dialog', { name: '创建角色' }).getByRole('button', { name: /创\s*建/ }).click()

  expect(createdPayload).toMatchObject({
    writing_notes: '第一卷第八章埋下家族线索',
    speech_patterns: '称呼他人全名，句尾常停顿',
    motivations: '守住边城并查清旧案',
    arc_summary: '从被动守城到主动揭露真相',
    card_version: 2,
  })

  const createdCard = page.locator('.ant-card').filter({ hasText: '林澜' })
  await expect(createdCard).toContainText('写作卡片')
  await expect(createdCard).toContainText('v2')
  await expect(createdCard).toContainText('第一卷第八章埋下家族线索')

  await createdCard.locator('.ant-card-actions li').first().click()
  const editDialog = page.getByRole('dialog', { name: '编辑角色' })
  await editDialog.getByPlaceholder('概括成长、转折和阶段性变化...').fill('从守城者成长为揭露真相的主导者')
  await editDialog.getByRole('button', { name: /保\s*存/ }).click()
  expect(updatedPayload).toMatchObject({ arc_summary: '从守城者成长为揭露真相的主导者', card_version: 2 })
  await expect(createdCard).toContainText('从守城者成长为揭露真相的主导者')

  await page.locator('.ant-checkbox').nth(1).click()
  await page.getByRole('button', { name: '批量导出 (1)' }).click()
  await expect.poll(() => exportedPayload).toBeTruthy()
  expect(exportedPayload).toMatchObject({
    characters: [expect.objectContaining({
      writing_notes: '第一卷第八章埋下家族线索',
      speech_patterns: '称呼他人全名，句尾常停顿',
      motivations: '守住边城并查清旧案',
      arc_summary: '从守城者成长为揭露真相的主导者',
      card_version: 2,
    })],
  })

  await page.getByRole('button', { name: '导入' }).click()
  await expect(page.getByText('角色写作卡片字段会随原生JSON一并保留')).toBeVisible()
  await page.locator('input[type=file]').setInputFiles({
    name: 'character-card.json',
    mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify({ characters: [{ name: '沈砚' }] })),
  })
  await expect(page.locator('.ant-modal-confirm-title').filter({ hasText: '导入预览' })).toBeVisible()
  await page.getByRole('button', { name: '确认导入' }).click()
  await expect(page.locator('.ant-modal-confirm-title').filter({ hasText: '导入完成' })).toBeVisible()

  const importedCard = page.locator('.ant-card').filter({ hasText: '沈砚' })
  await expect(importedCard).toContainText('导入后保留的伏笔备注')
  await expect(importedCard).toContainText('短句收束，少用感叹')
  await expect(importedCard).toContainText('寻找失踪的师父')
  await expect(importedCard).toContainText('从旁观者成长为主动破局者')
  await expect(importedCard).toContainText('v3')
})
