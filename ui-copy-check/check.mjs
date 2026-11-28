#!/usr/bin/env node
// Checks that screens do not grow small print. Project-agnostic: each project lists its screens in ui-copy.json.
//   node check.mjs [--config ui-copy.json] [--update]
// Per screen it measures, within the first viewport:
//   small       visible text pieces at or below `smallPx` (default 13px); fails above the baseline, so small print only goes down
//   duplicates  the same number shown twice (e.g. "$71,221" as headline and again as a label); fails unless listed in `allowDuplicates`
//   banned      words that must not appear on this screen (what belongs one level deeper); fails when present
//   required    words that must appear (e.g. a warning only an abnormal state shows); fails when missing
// Baselines live next to the config in ui-copy.baseline.json; --update rewrites them from this run.
// Exit codes: 0 pass, 1 a check failed, 2 bad config or the browser could not be driven.
import { spawn } from 'node:child_process'
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'

const CHROME = process.env.CHROME_PATH ?? '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

function die(message) {
  console.error(`ui-copy-check: ${message}`)
  process.exit(2)
}

/** Runs in the page. Only text a person sees on the first screen counts. */
const MEASURE = String(async ({ smallPx, banned, required, allowDuplicates }) => {
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))
  const items = []
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT)
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const text = node.textContent.replace(/\s+/g, ' ').trim()
    const el = node.parentElement
    if (!text || !el || el.closest('[hidden], script, style, noscript, template, [aria-hidden="true"]')) continue
    const style = getComputedStyle(el)
    if (style.visibility !== 'visible' || el.checkVisibility?.({ opacityProperty: true }) === false) continue
    const range = document.createRange()
    range.selectNodeContents(node)
    const r = range.getBoundingClientRect()
    if (!r.width || !r.height || r.bottom <= 0 || r.top >= innerHeight || r.right <= 0 || r.left >= innerWidth) continue
    items.push({ text, px: parseFloat(style.fontSize) })
  }
  const counts = new Map()
  for (const { text } of items) {
    for (const [n] of text.matchAll(/[$€¥£]?\d[\d,]*(?:\.\d+)?%?/g)) {
      // Short bare integers ("#1", "2 个") repeat naturally; amounts, prices and percentages should not.
      if (!/[.,%$€¥£]/.test(n) && n.length < 3) continue
      if (!allowDuplicates.includes(n)) counts.set(n, (counts.get(n) ?? 0) + 1)
    }
  }
  const all = items.map((i) => i.text).join('\n')
  const small = items.filter((i) => i.px <= smallPx).map((i) => i.text)
  return {
    small: small.length,
    smallTexts: small,
    duplicates: [...counts].filter(([, c]) => c > 1).map(([n, c]) => `${n} ×${c}`),
    banned: banned.filter((w) => all.includes(w)),
    missing: required.filter((w) => !all.includes(w)),
  }
})

class Page {
  static async open(wsUrl) {
    const page = new Page()
    page.ws = new WebSocket(wsUrl)
    page.next = 0
    page.waiting = new Map()
    page.events = []
    await new Promise((ok, fail) => {
      page.ws.onopen = ok
      page.ws.onerror = () => fail(new Error(`连不上 ${wsUrl}`))
    })
    page.ws.onmessage = (e) => {
      const msg = JSON.parse(e.data)
      if (msg.id) page.waiting.get(msg.id)?.(msg)
      else page.events.push(msg.method)
    }
    return page
  }
  send(method, params = {}) {
    const id = ++this.next
    this.ws.send(JSON.stringify({ id, method, params }))
    return new Promise((ok, fail) =>
      this.waiting.set(id, (msg) => (msg.error ? fail(new Error(`${method}: ${msg.error.message}`)) : ok(msg.result))),
    )
  }
  async evaluate(expression) {
    const r = await this.send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true })
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text)
    return r.result.value
  }
  async goto(url) {
    this.events = []
    await this.send('Page.navigate', { url })
    for (let i = 0; i < 150 && !this.events.includes('Page.loadEventFired'); i++) await sleep(100)
  }
  close() {
    this.ws.close()
  }
}

async function launchChrome() {
  if (!existsSync(CHROME)) die(`找不到 Chrome：${CHROME}（可用 CHROME_PATH 指定）`)
  const profile = mkdtempSync(join(tmpdir(), 'ui-copy-check-'))
  const proc = spawn(CHROME, ['--headless=new', '--remote-debugging-port=0', `--user-data-dir=${profile}`, '--no-first-run', '--hide-scrollbars', 'about:blank'], {
    stdio: 'ignore',
  })
  const portFile = join(profile, 'DevToolsActivePort')
  for (let i = 0; i < 100 && !existsSync(portFile); i++) await sleep(100)
  if (!existsSync(portFile)) die('Chrome 没有启动')
  const port = readFileSync(portFile, 'utf8').split('\n')[0]
  return {
    endpoint: `http://127.0.0.1:${port}`,
    stop: async () => {
      const exited = new Promise((r) => proc.once('exit', r))
      proc.kill()
      await exited
      rmSync(profile, { recursive: true, force: true, maxRetries: 5 })
    },
  }
}

async function pageTarget(endpoint) {
  for (let i = 0; i < 50; i++) {
    const list = await fetch(`${endpoint}/json/list`).then((r) => r.json()).catch(() => [])
    const page = list.find((t) => t.type === 'page')
    if (page) return page.webSocketDebuggerUrl
    await sleep(100)
  }
  die(`${endpoint} 上没有页面`)
}

function loadConfig(path) {
  if (!existsSync(path)) die(`找不到配置 ${path}`)
  const config = JSON.parse(readFileSync(path, 'utf8'))
  if (!Array.isArray(config.screens) || config.screens.length === 0) die('配置里没有 screens')
  for (const s of config.screens) {
    if (!s.name || (!s.url && !s.setup)) die(`screen 需要 name，以及 url 或 setup：${JSON.stringify(s)}`)
  }
  return config
}

async function main() {
  const args = process.argv.slice(2)
  const configPath = resolve(args.includes('--config') ? args[args.indexOf('--config') + 1] : 'ui-copy.json')
  const update = args.includes('--update')
  const config = loadConfig(configPath)
  const baselinePath = join(dirname(configPath), 'ui-copy.baseline.json')
  const baseline = existsSync(baselinePath) ? JSON.parse(readFileSync(baselinePath, 'utf8')) : {}
  const viewport = config.viewport ?? { width: 1280, height: 800 }

  // `cdp` attaches to a running browser or Electron app instead of launching Chrome.
  const chrome = config.cdp ? null : await launchChrome()
  const page = await Page.open(await pageTarget(config.cdp ?? chrome.endpoint))
  const results = {}
  let failed = false
  try {
    await page.send('Page.enable')
    await page.send('Emulation.setDeviceMetricsOverride', { ...viewport, deviceScaleFactor: 1, mobile: false })
    for (const s of config.screens) {
      if (s.url) await page.goto(new URL(s.url, `file://${dirname(configPath)}/`).href)
      if (s.setup) await page.evaluate(`(async () => { ${s.setup} })()`)
      const m = await page.evaluate(
        `(${MEASURE})(${JSON.stringify({ smallPx: config.smallPx ?? 13, banned: s.banned ?? [], required: s.required ?? [], allowDuplicates: s.allowDuplicates ?? [] })})`,
      )
      results[s.name] = m
      const limit = baseline[s.name]?.small
      const problems = [
        ...(limit === undefined && !update ? [`没有基线（先跑 --update）`] : []),
        ...(limit !== undefined && m.small > limit && !update ? [`小字 ${m.small} 条，超过基线 ${limit}`] : []),
        ...m.duplicates.map((d) => `同屏重复的数字：${d}`),
        ...m.banned.map((w) => `不该出现：${w}`),
        ...m.missing.map((w) => `应该出现：${w}`),
      ]
      failed ||= problems.length > 0
      const note = limit !== undefined && m.small < limit ? `（可下调基线 ${limit} → ${m.small}）` : ''
      console.log(`${problems.length ? 'FAIL' : 'PASS'}  ${s.name}：小字 ${m.small} 条${note}`)
      for (const p of problems) console.log(`      ${p}`)
    }
  } finally {
    await page.send('Emulation.clearDeviceMetricsOverride').catch(() => undefined)
    page.close()
    await chrome?.stop()
  }
  if (update) {
    writeFileSync(baselinePath, `${JSON.stringify(Object.fromEntries(Object.entries(results).map(([k, v]) => [k, { small: v.small, texts: v.smallTexts }])), null, 2)}\n`)
    console.log(`已写入基线 ${baselinePath}`)
  }
  process.exit(failed ? 1 : 0)
}

main().catch((err) => die(err instanceof Error ? err.message : String(err)))
