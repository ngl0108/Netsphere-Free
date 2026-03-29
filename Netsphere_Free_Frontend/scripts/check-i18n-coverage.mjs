import fs from 'fs';
import path from 'path';
import process from 'process';
import { fileURLToPath } from 'url';
import { messages as baseMessages } from '../src/i18n/messages.js';
import { patchMessages } from '../src/i18n/patchMessages.js';
import { safeMessages } from '../src/i18n/safeMessages.js';
import { finalMessages } from '../src/i18n/finalMessages.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const rootDir = path.resolve(__dirname, '..');
const strict = process.argv.includes('--strict');

const isCorruptedText = (value) => {
  const text = String(value || '');
  if (!text) return false;
  if (text.includes('\uFFFD')) return true;
  const questionMarks = (text.match(/\?/g) || []).length;
  if (questionMarks >= 2) return true;
  if (/\?[\u3131-\u314E\u314F-\u3163\uAC00-\uD7A3]/.test(text)) return true;
  return false;
};

const mergeLocaleMessages = (locale) => {
  const out = {};
  const sources = [baseMessages, patchMessages, safeMessages, finalMessages];
  for (const source of sources) {
    const group = source?.[locale];
    if (!group || typeof group !== 'object') continue;
    for (const [key, value] of Object.entries(group)) {
      if (locale === 'ko' && isCorruptedText(value)) continue;
      out[key] = value;
    }
  }
  return out;
};

const merged = {
  en: mergeLocaleMessages('en'),
  ko: mergeLocaleMessages('ko'),
};

const walkFiles = (dir, out = []) => {
  if (!fs.existsSync(dir)) return out;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      walkFiles(full, out);
      continue;
    }
    if (/\.(jsx|js|tsx|ts)$/.test(entry.name)) {
      out.push(full);
    }
  }
  return out;
};

const sourceFiles = [
  ...walkFiles(path.join(rootDir, 'src', 'pages')),
  ...walkFiles(path.join(rootDir, 'src', 'components')),
  ...walkFiles(path.join(rootDir, 'src', 'context')),
  path.join(rootDir, 'src', 'App.jsx'),
].filter((p) => fs.existsSync(p));

const extractI18nKeys = (content) => {
  const keys = [];
  const re = /\bt\(\s*['"`]([^'"`]+)['"`]/g;
  let m = null;
  while ((m = re.exec(content))) {
    const key = String(m[1] || '').trim();
    if (!key) continue;
    if (key.includes('${')) continue;
    keys.push(key);
  }
  return keys;
};

const extractHardcodedCandidates = (content, filePath) => {
  const rows = [];
  const lines = content.split(/\r?\n/);
  const attrRe = /\b(placeholder|title|aria-label)\s*=\s*"([^"{][^"]*[A-Za-z\uAC00-\uD7A3][^"]*)"/g;
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    let m = null;
    while ((m = attrRe.exec(line))) {
      rows.push({
        file: filePath,
        line: i + 1,
        kind: m[1],
        value: m[2].trim(),
      });
    }
  }
  return rows;
};

const usedKeys = new Set();
const hardcoded = [];
for (const file of sourceFiles) {
  const content = fs.readFileSync(file, 'utf8');
  for (const key of extractI18nKeys(content)) {
    usedKeys.add(key);
  }
  hardcoded.push(...extractHardcodedCandidates(content, path.relative(rootDir, file)));
}

const usedList = Array.from(usedKeys).sort();
const missingEn = usedList.filter((k) => !(k in (merged.en || {})));
const missingKo = usedList.filter((k) => !(k in (merged.ko || {})));
const corruptedKo = usedList.filter((k) => isCorruptedText(merged.ko?.[k]));

const printList = (title, rows, limit = 80) => {
  console.log(`\n${title}: ${rows.length}`);
  for (const row of rows.slice(0, limit)) {
    console.log(`- ${typeof row === 'string' ? row : `${row.file}:${row.line} [${row.kind}] ${row.value}`}`);
  }
  if (rows.length > limit) {
    console.log(`... and ${rows.length - limit} more`);
  }
};

console.log(`Scanned files: ${sourceFiles.length}`);
console.log(`Used i18n keys: ${usedList.length}`);
printList('Missing keys (EN)', missingEn);
printList('Missing keys (KO)', missingKo);
printList('Corrupted KO values', corruptedKo);
printList('Hardcoded attribute candidates', hardcoded, 120);

if (strict) {
  const hasBlocking = missingEn.length > 0 || missingKo.length > 0 || corruptedKo.length > 0;
  if (hasBlocking) process.exitCode = 1;
}
