/**
 * Smoke test against a running, seeded server:
 *   cd ../server && uv run python manage.py seed_demo && uv run daphne -p 8000 config.asgi:application
 *   npm run e2e
 *
 * The second test changes data (it creates the "Hash Tables" node); re-run `seed_demo --reset` to repeat it.
 */
import { _electron as electron, expect, test, type ElectronApplication, type Page } from '@playwright/test'
import { mkdtempSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'

const SERVER = process.env.AIB_SERVER_URL ?? 'http://127.0.0.1:8000'
const SHOTS = process.env.E2E_SCREENSHOT_DIR ?? 'test-results'

test('professor opens the Live class and sees the graph', async () => {
  const app = await electron.launch({
    args: ['.'],
    env: { ...process.env, AIB_SERVER_URL: SERVER, AIB_USER_DATA: mkdtempSync(join(tmpdir(), 'aib-e2e-')) }
  })
  const page = await app.firstWindow()
  await page.setViewportSize({ width: 1400, height: 900 }).catch(() => undefined)

  await page.fill('input[name=email]', 'prof@demo.local')
  await page.fill('input[name=password]', 'demo1234')
  await page.click('button[type=submit]')
  await expect(page.getByTestId('current-user')).toHaveText('Prof. Marina Costa')

  await page.getByTestId('class-card').filter({ hasText: 'Live' }).click()
  await expect(page.getByTestId('graph-canvas')).toBeVisible()
  await expect(page.getByTestId('graph-node').first()).toBeVisible()
  const count = await page.getByTestId('graph-node').count()
  expect(count).toBeGreaterThanOrEqual(12)

  await page.getByTestId('graph-node').filter({ hasText: 'Stacks and Queues' }).click()
  await expect(page.locator('.node-title')).toHaveText('Stacks and Queues')
  await page.screenshot({ path: join(SHOTS, 'graph-professor.png') })

  await page.getByRole('button', { name: 'Dashboard' }).click()
  await expect(page.getByText('Participation')).toBeVisible()
  await page.waitForTimeout(800)
  await page.screenshot({ path: join(SHOTS, 'dashboard-professor.png') })

  await app.close()
})

async function launchAs(email: string): Promise<{ app: ElectronApplication; page: Page }> {
  const app = await electron.launch({
    args: ['.'],
    env: { ...process.env, AIB_SERVER_URL: SERVER, AIB_USER_DATA: mkdtempSync(join(tmpdir(), 'aib-e2e-')) }
  })
  const page = await app.firstWindow()
  await page.fill('input[name=email]', email)
  await page.fill('input[name=password]', 'demo1234')
  await page.click('button[type=submit]')
  await expect(page.getByTestId('current-user')).toBeVisible()
  await page.getByTestId('class-card').filter({ hasText: 'Live' }).click()
  await expect(page.getByTestId('graph-node').first()).toBeVisible()
  return { app, page }
}

test('a student question creates a node that the professor sees live', async () => {
  const prof = await launchAs('prof@demo.local')
  const student = await launchAs('bruno@demo.local')
  try {
    const hashNode = (p: Page) => p.getByTestId('graph-node').filter({ hasText: 'Hash Tables' })
    test.skip((await hashNode(prof.page).count()) > 0, 'Hash Tables already exists; reseed with seed_demo --reset')

    await student.page.getByTestId('graph-node').filter({ hasText: 'Stacks and Queues' }).click()
    await student.page.getByTestId('question-input').fill('How do hash tables handle collisions?')
    await student.page.getByRole('button', { name: 'Ask' }).click()
    await expect(student.page.getByText('Your question created a new node')).toBeVisible({ timeout: 20_000 })
    await expect(hashNode(student.page)).toBeVisible()

    // Arrives in the professor's window through the websocket, without a reload.
    await expect(hashNode(prof.page)).toBeVisible({ timeout: 10_000 })
    await student.page.screenshot({ path: join(SHOTS, 'graph-student-question.png') })
    await prof.page.screenshot({ path: join(SHOTS, 'graph-professor-live.png') })
  } finally {
    await student.app.close()
    await prof.app.close()
  }
})
