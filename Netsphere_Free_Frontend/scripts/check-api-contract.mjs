import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const repoRoot = path.resolve(process.cwd(), '..');
const servicesPath = path.resolve(process.cwd(), 'src', 'api', 'services.js');
const snapshotPath = path.resolve(repoRoot, 'Netsphere_Free_Backend', 'tests', 'contracts', 'openapi.snapshot.json');

const normalizePath = (value) => {
  let out = String(value || '').trim();
  out = out.replace(/\$\{[^}]+\}/g, '{param}');
  out = out.replace(/\{[^}/]+\}/g, '{param}');
  out = out.split('?')[0].trim();
  if (out.length > 1 && out.endsWith('/')) out = out.slice(0, -1);
  return out;
};

const readJson = (filePath) => JSON.parse(fs.readFileSync(filePath, 'utf8'));

const extractFrontendContracts = (sourceText) => {
  const re = /api\.(get|post|put|patch|delete)\(\s*(`[^`]*`|'[^']*'|"[^"]*")/gs;
  const found = new Set();
  let match;
  while ((match = re.exec(sourceText)) !== null) {
    const method = String(match[1] || '').toLowerCase().trim();
    const literal = String(match[2] || '');
    if (literal.length < 2) continue;
    let rawPath = normalizePath(literal.slice(1, -1));
    if (!rawPath.startsWith('/')) continue;
    if (!rawPath.startsWith('/api/v1')) rawPath = `/api/v1${rawPath}`;
    found.add(`${method} ${rawPath}`);
  }
  return found;
};

const extractOpenApiContracts = (schema) => {
  const found = new Set();
  const paths = schema?.paths || {};
  for (const [rawPath, methods] of Object.entries(paths)) {
    const normalizedPath = normalizePath(rawPath);
    if (!methods || typeof methods !== 'object') continue;
    for (const method of Object.keys(methods)) {
      const m = String(method || '').toLowerCase().trim();
      if (!['get', 'post', 'put', 'patch', 'delete'].includes(m)) continue;
      found.add(`${m} ${normalizedPath}`);
    }
  }
  return found;
};

if (!fs.existsSync(servicesPath)) {
  console.error(`Frontend services file not found: ${servicesPath}`);
  process.exit(1);
}
if (!fs.existsSync(snapshotPath)) {
  console.error(`OpenAPI snapshot not found: ${snapshotPath}`);
  process.exit(1);
}

const servicesSource = fs.readFileSync(servicesPath, 'utf8');
const frontendContracts = extractFrontendContracts(servicesSource);
const openapiContracts = extractOpenApiContracts(readJson(snapshotPath));

const missing = [...frontendContracts].filter((entry) => !openapiContracts.has(entry)).sort();
if (missing.length > 0) {
  console.error('Frontend API contract mismatch: services.js references endpoints not in OpenAPI snapshot.');
  for (const entry of missing.slice(0, 120)) {
    console.error(`- ${entry}`);
  }
  process.exit(1);
}

console.log(`Frontend API contract check passed (${frontendContracts.size} endpoints).`);
