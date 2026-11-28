// node --test tests/test_ui_copy_check.mjs   (needs Google Chrome)
import { spawnSync } from 'node:child_process'
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { test } from 'node:test'
import assert from 'node:assert/strict'

const root = new URL('..', import.meta.url).pathname
const check = join(root, 'ui-copy-check/check.mjs')
const fixture = (f) => `file://${join(root, 'tests/ui-copy', f)}`

function run(screens, { update = false, baseline } = {}) {
  const dir = mkdtempSync(join(tmpdir(), 'ui-copy-test-'))
  writeFileSync(join(dir, 'ui-copy.json'), JSON.stringify({ screens }))
  if (baseline) writeFileSync(join(dir, 'ui-copy.baseline.json'), JSON.stringify(baseline))
  const r = spawnSync('node', [check, ...(update ? ['--update'] : [])], { cwd: dir, encoding: 'utf8', timeout: 60_000 })
  const saved = update ? JSON.parse(readFileSync(join(dir, 'ui-copy.baseline.json'), 'utf8')) : null
  return { code: r.status, out: r.stdout + r.stderr, saved }
}

test('counts only small text a person sees on the first screen', () => {
  const r = run([{ name: 'clean', url: fixture('clean.html') }], { update: true })
  assert.equal(r.code, 0, r.out)
  assert.deepEqual(r.saved.clean, { small: 1, texts: ['现价 $96,000'] })
})

test('passes at the baseline and fails when small print grows', () => {
  const baseline = { s: { small: 1 } }
  assert.equal(run([{ name: 's', url: fixture('clean.html') }], { baseline }).code, 0)
  const r = run([{ name: 's', url: fixture('noisy.html'), allowDuplicates: ['$71,221'] }], { baseline })
  assert.equal(r.code, 1)
  assert.match(r.out, /小字 5 条，超过基线 1/)
})

test('says when the baseline can come down', () => {
  const r = run([{ name: 's', url: fixture('clean.html') }], { baseline: { s: { small: 3 } } })
  assert.equal(r.code, 0)
  assert.match(r.out, /可下调基线 3 → 1/)
})

test('flags a number shown twice unless allowed', () => {
  const screens = (allow) => [{ name: 's', url: fixture('noisy.html'), allowDuplicates: allow }]
  const baseline = { s: { small: 9 } }
  const r = run(screens([]), { baseline })
  assert.equal(r.code, 1)
  assert.match(r.out, /同屏重复的数字：\$71,221 ×2/)
  assert.equal(run(screens(['$71,221']), { baseline }).code, 0)
})

test('banned words must be absent and required words present', () => {
  const baseline = { s: { small: 9 } }
  const base = { name: 's', url: fixture('noisy.html'), allowDuplicates: ['$71,221'] }
  const r = run([{ ...base, banned: ['HF', 'Passphrase'], required: ['刷新失败'] }], { baseline })
  assert.equal(r.code, 1)
  assert.match(r.out, /不该出现：HF/)
  assert.doesNotMatch(r.out, /不该出现：Passphrase/)
  assert.match(r.out, /应该出现：刷新失败/)
})

test('root limits the check to one element', () => {
  const base = { name: 's', url: fixture('noisy.html'), allowDuplicates: ['$71,221'], banned: ['导航'] }
  const whole = run([base], { update: true })
  assert.equal(whole.saved.s.small, 5)
  assert.match(whole.out, /不该出现：导航/)
  const main = run([{ ...base, root: 'main' }], { update: true })
  assert.equal(main.saved.s.small, 4)
  assert.doesNotMatch(main.out, /不该出现/)
})

test('a screen without a baseline fails until --update', () => {
  const r = run([{ name: 'new', url: fixture('clean.html') }])
  assert.equal(r.code, 1)
  assert.match(r.out, /没有基线/)
})

test('bad config exits 2', () => {
  assert.equal(run([{ name: 'x' }]).code, 2)
})
