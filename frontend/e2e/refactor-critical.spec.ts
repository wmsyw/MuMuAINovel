import { expect, test, type Page, type Route } from '@playwright/test'

const now = '2026-07-20T12:00:00.000Z'

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
}

async function stubProjectShell(page: Page) {
  await page.route('**/api/**', route => fulfillJson(route, {}))
  await page.route('**/api/auth/user', route => fulfillJson(route, {
    user_id: 'user-e2e',
    username: 'e2e',
    display_name: 'E2E作者',
    trust_level: 1,
    is_admin: false,
    created_at: now,
    last_login: now,
  }))
  await page.route('**/api/projects/1', route => fulfillJson(route, {
    id: '1',
    title: '重构验收项目',
    description: 'critical refactor flow',
    theme: '成长',
    genre: '玄幻',
    target_words: 100000,
    current_words: 18,
    status: 'writing',
    wizard_status: 'completed',
    outline_mode: 'one-to-many',
    created_at: now,
    updated_at: now,
  }))
  await page.route('**/api/settings/feature-flags', route => fulfillJson(route, { local_assets_enabled: false }))
  await page.route('**/api/outlines/project/1', route => fulfillJson(route, { total: 0, items: [] }))
  await page.route('**/api/characters/project/1**', route => fulfillJson(route, { total: 0, items: [] }))
  await page.route('**/api/chapters/project/1', route => fulfillJson(route, {
    total: 1,
    items: [{
      id: 'chapter-1',
      project_id: '1',
      title: '初入宗门',
      content: '李云飞加入青云宗，成为剑修。',
      summary: '',
      chapter_number: 1,
      word_count: 18,
      status: 'completed',
      sub_index: 1,
      created_at: now,
      updated_at: now,
    }],
  }))
  await page.route('**/api/writing-styles/project/1', route => fulfillJson(route, { styles: [] }))
  await page.route('**/api/chapters/project/1/batch-generate/active', route => fulfillJson(route, { has_active_task: false }))
  await page.route('**/api/chapters/project/1/analysis-statuses**', route => fulfillJson(route, { items: {} }))
  await page.route('**/api/tasks?**', route => fulfillJson(route, { items: [] }))
}

test('submits platform and multidimensional filters to batch inspiration generation', async ({ page }) => {
  let batchPayload: Record<string, unknown> | undefined

  await page.route('**/api/**', route => fulfillJson(route, { items: [], total: 0 }))
  await page.route('**/api/auth/user', route => fulfillJson(route, {
    user_id: 'e2e-user',
    username: 'admin',
    display_name: '管理员',
    trust_level: 4,
    is_admin: true,
    created_at: now,
    last_login: now,
  }))
  await page.route('**/api/auth/config', route => fulfillJson(route, {
    local_auth_enabled: true,
    linuxdo_enabled: false,
    email_auth_enabled: false,
    email_register_enabled: false,
  }))
  await page.route('**/api/inspiration/batch-generate', async route => {
    batchPayload = route.request().postDataJSON() as Record<string, unknown>
    const cards = ['星门守夜人', '废土藏书阁', '逆流炼星师'].map((title, index) => ({
      id: `card-${index + 1}`,
      title,
      hook: `${title}的开篇钩子`,
      genre: ['玄幻'],
      world_setting: '灵气复苏后的废土城邦',
      core_conflict: '守护与自由的冲突',
      protagonist: '失去记忆的守门人',
      golden_finger: '读取遗物记忆',
      opening_hook: '第一夜星门意外开启',
      selling_points: ['升级体系', '谜团推进'],
      risks: ['设定复杂'],
    }))
    await fulfillJson(route, {
      ideas: cards,
      generation_meta: {
        count: 3,
        requested_count: 3,
        platform: 'qidian',
        filters: {
          genre_tags: ['玄幻', '东方仙侠'],
          plot_keywords: ['废土'],
          character_traits: ['天才'],
        },
        warnings: [],
      },
    })
  })

  await page.goto('/inspiration')
  await page.getByRole('combobox').click()
  await page.getByRole('combobox').press('Home')
  await page.getByRole('combobox').press('Enter')
  await page.getByText('男频', { exact: true }).click()
  await page.getByRole('button', { name: '下一步：选择题材' }).click()
  await page.getByRole('combobox').click()
  await page.getByRole('combobox').press('Home')
  await page.getByRole('combobox').press('Enter')
  await page.getByRole('button', { name: '下一步：选择标签' }).click()
  await page.getByText('东方仙侠', { exact: true }).click()
  await page.getByText('天才', { exact: true }).click()
  await page.getByText('废土', { exact: true }).click()
  await page.getByRole('button', { name: '下一步：补充剧情简述' }).click()
  await page.getByPlaceholder(/主角在灵气复苏/).fill('主角守护一扇会吞噬记忆的星门')
  await page.getByRole('button', { name: '生成故事方向' }).click()

  await expect(page.getByText('推荐书名：星门守夜人', { exact: true })).toBeVisible()
  expect(batchPayload).toMatchObject({
    platform: 'qidian',
    genre_tags: ['玄幻', '东方仙侠'],
    plot_keywords: ['废土'],
    character_traits: ['天才'],
    count: 3,
  })
})

test('applies a world template and opens its dynamic fields for editing', async ({ page }) => {
  await stubProjectShell(page)
  const template = {
    id: 'template-sci-fi',
    name: '科幻世界',
    category: '科幻',
    fields: {
      time_period: { label: '时代', type: 'text', required: true },
      rules: { label: '世界规则', type: 'textarea', required: true },
    },
    example_data: {
      time_period: '星历 2478 年',
      rules: '超光速通信不可用',
    },
    is_system: true,
  }
  let appliedTemplateId = ''

  await page.route('**/api/world-setting/templates', route => fulfillJson(route, { total: 1, items: [template] }))
  await page.route('**/api/world-setting/apply-template', async route => {
    const payload = route.request().postDataJSON() as { template_id: string }
    appliedTemplateId = payload.template_id
    await fulfillJson(route, {
      project_id: '1',
      template,
      world_setting_data: {
        template_id: template.id,
        template_name: template.name,
        fields: template.fields,
        values: template.example_data,
      },
    })
  })

  await page.goto('/project/1/world-setting')
  await page.getByRole('button', { name: '选择模板' }).click()
  await expect(page.getByText('科幻世界', { exact: true })).toBeVisible()
  await page.getByRole('button', { name: '应用并编辑' }).click()

  await expect(page.getByText('手动编辑当前生效世界观')).toBeVisible()
  await expect(page.getByLabel('时代')).toHaveValue('星历 2478 年')
  await expect(page.getByLabel('世界规则')).toHaveValue('超光速通信不可用')
  expect(appliedTemplateId).toBe('template-sci-fi')
})

test('reviews extracted entities and keeps dark responsive project shell usable', async ({ page }) => {
  const candidates = [
    {
      id: 'candidate-org',
      run_id: 'run-1',
      project_id: '1',
      user_id: 'user-e2e',
      source_chapter_id: 'chapter-1',
      candidate_type: 'organization',
      trigger_type: 'chapter_acceptance',
      source_hash: 'hash-1',
      display_name: '青云宗',
      normalized_name: '青云宗',
      canonical_target_type: 'organization',
      canonical_target_id: null,
      status: 'pending',
      confidence: 0.95,
      evidence_text: '李云飞加入青云宗',
      source_start_offset: 5,
      source_end_offset: 8,
      source_chapter_number: 1,
      source_chapter_order: 1,
      payload: {},
      raw_payload: {},
      created_at: now,
      updated_at: now,
    },
    {
      id: 'candidate-career',
      run_id: 'run-1',
      project_id: '1',
      user_id: 'user-e2e',
      source_chapter_id: 'chapter-1',
      candidate_type: 'profession',
      trigger_type: 'chapter_acceptance',
      source_hash: 'hash-2',
      display_name: '剑修',
      normalized_name: '剑修',
      canonical_target_type: 'career',
      canonical_target_id: null,
      status: 'pending',
      confidence: 0.93,
      evidence_text: '成为剑修',
      source_start_offset: 11,
      source_end_offset: 13,
      source_chapter_number: 1,
      source_chapter_order: 1,
      payload: {},
      raw_payload: {},
      created_at: now,
      updated_at: now,
    },
  ]
  let acceptedIds: string[] = []

  await stubProjectShell(page)
  await page.route('**/api/extraction/candidates?**', route => fulfillJson(route, {
    total: candidates.length,
    items: candidates,
  }))
  await page.route('**/api/extraction/candidates/batch-accept', async route => {
    const payload = JSON.parse(route.request().postData() || '{}') as { candidate_ids: string[] }
    acceptedIds = payload.candidate_ids
    const reviewed = candidates.map(candidate => ({ ...candidate, status: 'accepted' }))
    candidates.splice(0, candidates.length)
    await fulfillJson(route, { changed: reviewed.length, failures: [], candidates: reviewed })
  })

  await page.goto('/project/1/chapters')
  await expect(page.getByRole('button', { name: /实体提取审核/ })).toBeVisible()
  const navigationDuration = await page.evaluate(() => performance.getEntriesByType('navigation')[0]?.duration || 0)
  expect(navigationDuration).toBeLessThan(2_000)
  await page.getByRole('button', { name: /实体提取审核/ }).click()
  await expect(page.getByText('青云宗', { exact: true })).toBeVisible()
  await expect(page.getByText('剑修', { exact: true })).toBeVisible()

  await page.getByRole('button', { name: /全\s*选/ }).click()
  await page.getByRole('button', { name: /接受所选/ }).click()
  await page.locator('.ant-popconfirm-buttons .ant-btn-primary').click()
  await expect.poll(() => acceptedIds.sort()).toEqual(['candidate-career', 'candidate-org'])
  await expect(page.getByText('暂无待审核实体；章节标记完成后会自动提取')).toBeVisible()
  await page.locator('.ant-modal-close').click()

  await page.locator('.ant-segmented-item').filter({ has: page.locator('.anticon-moon') }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme-resolved', 'dark')
  await expect.poll(() => page.evaluate(() => getComputedStyle(document.body).backgroundColor)).toBe('rgb(15, 17, 21)')

  await page.setViewportSize({ width: 390, height: 844 })
  await expect(page.getByRole('button', { name: 'menu-unfold' })).toBeVisible()
  await expect(page.locator('.ant-layout-sider')).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBe(0)
})
