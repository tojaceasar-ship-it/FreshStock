import { test, expect } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const freshStockUrl = 'https://frontend-navy-nu-73.vercel.app/'
const freshPosUrl = 'https://freshpos-two.vercel.app/'
const evidenceDir = path.resolve('..', 'audit', 'remote-evidence')

test('odkrycie wdrożonych FreshStock i FreshPOS w dwóch kartach', async ({ browser }) => {
  test.setTimeout(120_000)
  fs.mkdirSync(evidenceDir, { recursive: true })
  const context = await browser.newContext({ viewport: { width: 1600, height: 1000 } })
  const stock = await context.newPage()
  const pos = await context.newPage()

  await Promise.all([
    stock.goto(freshStockUrl, { waitUntil: 'domcontentloaded' }),
    pos.goto(freshPosUrl, { waitUntil: 'domcontentloaded' }),
  ])
  await Promise.all([stock.waitForTimeout(2500), pos.waitForTimeout(2500)])

  await stock.screenshot({ path: path.join(evidenceDir, '01-freshstock-start.png'), fullPage: true })
  await pos.screenshot({ path: path.join(evidenceDir, '02-freshpos-start.png'), fullPage: true })

  const inventory = {
    timestamp: new Date().toISOString(),
    freshstock: {
      url: stock.url(),
      title: await stock.title(),
      headings: await stock.getByRole('heading').allTextContents(),
      buttons: await stock.getByRole('button').allTextContents(),
      links: await stock.getByRole('link').allTextContents(),
    },
    freshpos: {
      url: pos.url(),
      title: await pos.title(),
      headings: await pos.getByRole('heading').allTextContents(),
      buttons: await pos.getByRole('button').allTextContents(),
      links: await pos.getByRole('link').allTextContents(),
    },
  }
  fs.writeFileSync(path.join(evidenceDir, 'discovery.json'), JSON.stringify(inventory, null, 2))
  expect(inventory.freshstock.title).toBeTruthy()
  expect(inventory.freshpos.title).toBeTruthy()
  await context.close()
})
