import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import process from 'node:process';
import { spawnSync, fork } from 'node:child_process';

const checks = [];

function pushCheck(name, ok, detail, hint = '') {
  checks.push({ name, ok: !!ok, detail: String(detail || ''), hint: String(hint || '') });
}

async function run() {
  const root = process.cwd();
  const browsersPath = process.env.PLAYWRIGHT_BROWSERS_PATH
    ? path.resolve(process.env.PLAYWRIGHT_BROWSERS_PATH)
    : path.join(os.homedir(), 'AppData', 'Local', 'ms-playwright');

  try {
    fs.mkdirSync(browsersPath, { recursive: true });
    const probe = path.join(browsersPath, '.write-probe');
    fs.writeFileSync(probe, 'ok', 'utf8');
    fs.unlinkSync(probe);
    pushCheck('browser-cache-writable', true, browsersPath);
  } catch (err) {
    pushCheck(
      'browser-cache-writable',
      false,
      `${browsersPath} :: ${err?.message || err}`,
      'Set PLAYWRIGHT_BROWSERS_PATH to a writable directory and reinstall browsers.',
    );
  }

  const forkTarget = path.join(root, 'scripts', '.doctor-fork-child.js');
  try {
    fs.writeFileSync(forkTarget, "process.exit(0);\n", 'utf8');
    const res = await awaitFork(forkTarget);
    if (res.ok) {
      pushCheck('node-fork-permission', true, 'child_process.fork works');
    } else {
      pushCheck(
        'node-fork-permission',
        false,
        res.error || 'fork failed',
        'Local security policy (Defender/AppLocker/EDR) may block node child process spawn.',
      );
    }
  } finally {
    try { fs.unlinkSync(forkTarget); } catch {}
  }

  const pw = spawnSync('node', ['./node_modules/@playwright/test/cli.js', '--version'], {
    cwd: root,
    encoding: 'utf8',
  });
  const pwDetail = (pw.stdout || pw.stderr || pw.error?.message || '').trim();
  pushCheck('playwright-cli', pw.status === 0, pwDetail || `status=${String(pw.status)}`);

  const failed = checks.filter((x) => !x.ok);
  for (const c of checks) {
    const mark = c.ok ? 'OK' : 'FAIL';
    console.log(`[${mark}] ${c.name}: ${c.detail}`);
    if (!c.ok && c.hint) console.log(`      hint: ${c.hint}`);
  }

  if (failed.length > 0) {
    console.log('\nRecommended recovery order:');
    console.log('1) Use Node 20 LTS (same as CI).');
    console.log('2) Set writable browser cache path: PLAYWRIGHT_BROWSERS_PATH=.pw-browsers');
    console.log('3) Run npm.cmd run e2e:install');
    console.log('4) If fork still fails, allow node.exe in Windows security policy and rerun.');
    process.exit(1);
  }

  console.log('\nE2E runtime looks healthy.');
  process.exit(0);
}

function awaitFork(target) {
  return new Promise((resolve) => {
    let settled = false;
    let child;
    try {
      child = fork(target, [], { stdio: 'ignore' });
    } catch (err) {
      resolve({ ok: false, error: err?.message || String(err) });
      return;
    }
    child.on('error', (err) => {
      if (settled) return;
      settled = true;
      resolve({ ok: false, error: err?.message || String(err) });
    });
    child.on('exit', (code) => {
      if (settled) return;
      settled = true;
      resolve({ ok: code === 0, error: code === 0 ? '' : `exit=${code}` });
    });
    setTimeout(() => {
      if (settled) return;
      settled = true;
      try { child.kill('SIGTERM'); } catch {}
      resolve({ ok: false, error: 'timeout while forking child process' });
    }, 5000);
  });
}

run().catch((err) => {
  console.error(`[FAIL] e2e-doctor fatal: ${err?.message || err}`);
  process.exit(2);
});
