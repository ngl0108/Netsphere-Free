import { spawn } from 'node:child_process';
import process from 'node:process';

const isWindows = process.platform === 'win32';
const cmd = isWindows ? 'cmd.exe' : 'npm';
const args = isWindows ? ['/d', '/s', '/c', 'npm run e2e:ops'] : ['run', 'e2e:ops'];

const child = spawn(cmd, args, {
  stdio: 'inherit',
  shell: false,
  env: {
    ...process.env,
    PW_SKIP_WEBSERVER: '1',
    E2E_BASE_URL: process.env.E2E_BASE_URL || 'http://127.0.0.1',
  },
});

child.on('error', (err) => {
  console.error(`[e2e:ops:docker] spawn failed: ${err?.message || err}`);
  process.exit(2);
});

child.on('exit', (code, signal) => {
  if (typeof code === 'number') process.exit(code);
  console.error(`[e2e:ops:docker] terminated by signal: ${signal || 'unknown'}`);
  process.exit(1);
});
