import { promises as fs } from 'node:fs';
import path from 'node:path';

const assetsDir = path.resolve(process.cwd(), 'dist', 'assets');

const budgetsKb = {
  entryJs: 320,
  genericJs: 350,
  workerJs: 1700,
  indexCss: 130,
  genericCss: 180,
};

const toKb = (bytes) => Number((bytes / 1024).toFixed(2));

const classify = (name) => {
  if (/^elk-worker\.min-.*\.js$/.test(name)) return { kind: 'workerJs', maxKb: budgetsKb.workerJs };
  if (/^index-.*\.js$/.test(name)) return { kind: 'entryJs', maxKb: budgetsKb.entryJs };
  if (/\.js$/.test(name)) return { kind: 'genericJs', maxKb: budgetsKb.genericJs };
  if (/^index-.*\.css$/.test(name)) return { kind: 'indexCss', maxKb: budgetsKb.indexCss };
  if (/\.css$/.test(name)) return { kind: 'genericCss', maxKb: budgetsKb.genericCss };
  return null;
};

const run = async () => {
  const stat = await fs.stat(assetsDir).catch(() => null);
  if (!stat || !stat.isDirectory()) {
    console.error(`[bundle-budget] dist assets directory not found: ${assetsDir}`);
    process.exit(1);
  }

  const names = await fs.readdir(assetsDir);
  const checks = [];
  const violations = [];

  for (const name of names) {
    const rule = classify(name);
    if (!rule) continue;
    const full = path.join(assetsDir, name);
    const info = await fs.stat(full);
    const sizeKb = toKb(info.size);
    checks.push({ name, sizeKb, maxKb: rule.maxKb, kind: rule.kind });
    if (sizeKb > rule.maxKb) {
      violations.push({ name, sizeKb, maxKb: rule.maxKb, kind: rule.kind });
    }
  }

  checks.sort((a, b) => b.sizeKb - a.sizeKb);
  const preview = checks.slice(0, 12);
  console.log('[bundle-budget] Top bundle assets (KB):');
  for (const row of preview) {
    console.log(`  - ${row.name}: ${row.sizeKb}KB (${row.kind}, max ${row.maxKb}KB)`);
  }

  if (violations.length > 0) {
    console.error('[bundle-budget] Budget violation(s) detected:');
    for (const v of violations) {
      console.error(`  - ${v.name}: ${v.sizeKb}KB > ${v.maxKb}KB (${v.kind})`);
    }
    process.exit(1);
  }

  console.log('[bundle-budget] All bundle budgets passed.');
};

run().catch((err) => {
  console.error(`[bundle-budget] failed: ${err?.stack || err}`);
  process.exit(1);
});

