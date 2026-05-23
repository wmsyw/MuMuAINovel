import { expect, test } from '@playwright/test'

test('root redirects to login and renders the public login surface', async ({ page }) => {
  await page.route('**/api/auth/user', async (route) => {
    await route.fulfill({
      status: 401,
      contentType: 'application/json',
      body: JSON.stringify({ detail: '未登录' }),
    })
  })

  await page.route('**/api/auth/config', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        local_auth_enabled: true,
        linuxdo_enabled: false,
        email_auth_enabled: false,
        email_register_enabled: false,
      }),
    })
  })

  await page.goto('/')

  await expect(page).toHaveURL(/\/login/)
  await expect(page.getByText('欢迎回来')).toBeVisible()
  await expect(page.getByRole('tab', { name: '本地登录' })).toBeVisible()
})
