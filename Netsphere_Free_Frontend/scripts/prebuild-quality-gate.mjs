import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const frontendDir = path.resolve(__dirname, '..');
const repoRoot = path.resolve(frontendDir, '..');
const gateScript = path.resolve(
  repoRoot,
  'Netsphere_Free_Backend',
  'tools',
  'run_local_quality_gate.py',
);
const venvPython =
  process.platform === 'win32'
    ? path.resolve(repoRoot, '.venv', 'Scripts', 'python.exe')
    : path.resolve(repoRoot, '.venv', 'bin', 'python');

if (process.env.SKIP_PREBUILD_GATE === '1') {
  console.log('[prebuild-gate] SKIP_PREBUILD_GATE=1, skipping gate.');
  process.exit(0);
}

if (!existsSync(gateScript)) {
  console.log('[prebuild-gate] Gate script not found, skipping gate.');
  process.exit(0);
}

const candidates =
  (existsSync(venvPython) ? [{ cmd: venvPython, args: [] }] : []).concat(
    process.platform === 'win32'
      ? [
        { cmd: 'python', args: [] },
        { cmd: 'py', args: ['-3'] },
      ]
      : [
        { cmd: 'python3', args: [] },
        { cmd: 'python', args: [] },
      ],
  );

const python = candidates.find((candidate) => {
  const probe = spawnSync(candidate.cmd, [...candidate.args, '--version'], {
    cwd: repoRoot,
    stdio: 'pipe',
  });
  return probe.status === 0;
});

if (!python) {
  console.log('[prebuild-gate] Python runtime not found, skipping gate.');
  process.exit(0);
}

console.log('[prebuild-gate] Running local quality gate before build...');
const gate = spawnSync(
  python.cmd,
  [...python.args, gateScript, '--skip-e2e', '--skip-build', '--skip-parser-benchmark'],
  {
    cwd: repoRoot,
    stdio: 'inherit',
    env: process.env,
  },
);

if (gate.status !== 0) {
  process.exit(gate.status ?? 1);
}

console.log('[prebuild-gate] Gate passed.');
