#!/usr/bin/env node
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { classifyChangedPaths } from './lib/gate_fast_plan.mjs';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const shell = process.platform === 'win32';

function resolveBaseRef() {
  const eventName = process.env.EVENT_NAME;
  const baseRef = process.env.BASE_REF;
  const beforeSha = process.env.BEFORE_SHA;
  const zeros = '0000000000000000000000000000000000000000';

  if (eventName === 'pull_request' && baseRef) {
    return 'origin/' + baseRef;
  }
  if (beforeSha && beforeSha !== zeros) {
    const check = spawnSync('git', ['cat-file', '-e', beforeSha + '^{commit}'], { cwd: repoRoot, shell });
    if (check.status === 0) {
      return beforeSha;
    }
  }
  const checkHead = spawnSync('git', ['rev-parse', '--verify', 'HEAD~1'], { cwd: repoRoot, shell });
  if (checkHead.status === 0) {
    return 'HEAD~1';
  }
  return null;
}

function getChangedFiles(base) {
  if (!base) return [];
  const diff = spawnSync('git', ['diff', '--name-only', base + '...HEAD'], {
    cwd: repoRoot,
    encoding: 'utf8',
    shell,
  });
  if (diff.status !== 0 || !diff.stdout) {
    const diff2 = spawnSync('git', ['diff', '--name-only', base, 'HEAD'], {
      cwd: repoRoot,
      encoding: 'utf8',
      shell,
    });
    if (diff2.status === 0 && diff2.stdout) {
      return diff2.stdout.split('\n').map((s) => s.trim()).filter(Boolean);
    }
    return [];
  }
  return diff.stdout.split('\n').map((s) => s.trim()).filter(Boolean);
}

const base = resolveBaseRef();
console.log('[ci-test-changed] Base ref for diff: ' + (base || 'none (running core guards only)'));

const changedFiles = getChangedFiles(base);
console.log(
  '[ci-test-changed] Changed files (' + changedFiles.length + '):\n' +
    (changedFiles.map((f) => '  - ' + f).join('\n') || '  (none)')
);

const classified = classifyChangedPaths(changedFiles);

// Core guards always executed for China distribution safety
const CORE_GUARDS = [
  'tests/desktop_download.test.ts',
  'tests/desktop_download_dom.test.ts',
  'tests/i18n_t_behavior.test.ts',
];

const targetTests = new Set(CORE_GUARDS);

for (const testFile of classified.testFiles) {
  targetTests.add(testFile);
}

const vitestBin = path.join(
  repoRoot,
  'node_modules',
  '.bin',
  process.platform === 'win32' ? 'vitest.cmd' : 'vitest'
);

let vitestArgs = [];
if (classified.relatedSources.length > 0) {
  console.log(
    '[ci-test-changed] Running related tests for sources:\n' +
      classified.relatedSources.map((s) => '  - ' + s).join('\n')
  );
  vitestArgs = [
    'related',
    ...classified.relatedSources,
    ...targetTests,
    '--run',
    '--passWithNoTests',
  ];
} else {
  console.log(
    '[ci-test-changed] No related sources changed. Running target guard & changed tests:\n' +
      [...targetTests].map((t) => '  - ' + t).join('\n')
  );
  vitestArgs = ['run', '--passWithNoTests', ...targetTests];
}

console.log('[ci-test-changed] Spawning: vitest ' + vitestArgs.join(' '));
const res = spawnSync(vitestBin, vitestArgs, {
  cwd: repoRoot,
  stdio: 'inherit',
  shell,
  env: process.env,
});

if (res.error) {
  console.error('[ci-test-changed] Error spawning vitest: ' + res.error.message);
  process.exit(1);
}

process.exit(res.status ?? 0);
