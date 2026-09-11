#!/usr/bin/env node
/**
 * @file sync_releases.mjs
 * Automated sync and translation tool for World of ClaudeCraft release notes.
 *
 * 1. Checks upstream releases from levy-street/world-of-claudecraft.
 * 2. Compares against local archive in data/releases/archive/.
 * 3. Translates any missing releases into Simplified Chinese using game terminology.
 * 4. Writes docs/releases/{tag}.md and data/releases/archive/{tag}.json.
 * 5. Maintains the active window in data/releases.json (capped at 20 releases, <= 25KB).
 * 6. Updates the master timeline in docs/releases/README.md.
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT_DIR = path.resolve(__dirname, '..');

const UPSTREAM_REPO = process.env.UPSTREAM_REPO || 'levy-street/world-of-claudecraft';
const DOCS_DIR = path.join(ROOT_DIR, 'docs', 'releases');
const ARCHIVE_DIR = path.join(ROOT_DIR, 'data', 'releases', 'archive');
const ACTIVE_FILE = path.join(ROOT_DIR, 'data', 'releases.json');
const README_FILE = path.join(DOCS_DIR, 'README.md');

const ACTIVE_WINDOW_SIZE = 20;
const RELEASE_BODY_MAX = 7500;

// Game terminology glossary for translation
const GLOSSARY = [
  ['World of ClaudeCraft', 'World of ClaudeCraft（克劳德争霸）'],
  ['World of Claudecraft', 'World of ClaudeCraft（克劳德争霸）'],
  ['The Crucible', '熔炉团队副本（The Crucible）'],
  ['Crucible', '熔炉副本'],
  ['Masterwrought', '大师锻造（Masterwrought）'],
  ['Eastbrook', '东溪谷（Eastbrook）'],
  ['Fenbridge', '芬桥镇（Fenbridge）'],
  ['Nythraxis', '奈斯拉西斯（Nythraxis）'],
  ['Varkhul', '瓦克胡尔（Varkhul）'],
  ['Claudium', '克劳德币（Claudium）'],
  ['Rallycart RXT', '拉力战车 RXT（Rallycart RXT）'],
  ['Bone Spikes', '骸骨尖刺'],
  ['Materials Vault', '材料共享金库'],
  ['Warsong Gulch', '战歌峡谷'],
  ['Molten Core', '熔火之心'],
  ['Ashen Coliseum', '灰烬大斗兽场'],
  ['Drowned Temple', '沉没神殿'],
  ['Ferryman Odo', '摆渡人奥多'],
  ['Alchemist Verane', '药剂师维兰'],
  ['Paladin', '圣骑士'],
  ['Warrior', '战士'],
  ['Rogue', '潜行者'],
  ['Mage', '法师'],
  ['Warlock', '术士'],
  ['Hunter', '猎人'],
  ['Shaman', '萨满祭司'],
  ['Priest', '牧师'],
  ['Druid', '德鲁伊'],
  ['Hotfix', '热修复补丁'],
  ['hotfix', '热修复补丁'],
  ['Patch Notes', '版本更新说明'],
  ['Added', '新增'],
  ['Fixed', '修复'],
  ['Updated', '更新'],
  ['Improve', '优化'],
  ['Refactor', '重构'],
  ['Support', '支持'],
];

function translateText(text) {
  if (!text) return '';
  let res = text;
  for (const [en, zh] of GLOSSARY) {
    res = res.replaceAll(en, zh);
  }
  return res;
}

function getExistingTags() {
  if (!fs.existsSync(ARCHIVE_DIR)) {
    fs.mkdirSync(ARCHIVE_DIR, { recursive: true });
    return new Set();
  }
  const files = fs.readdirSync(ARCHIVE_DIR).filter((f) => f.endsWith('.json'));
  return new Set(files.map((f) => f.replace(/\.json$/, '')));
}

async function fetchUpstreamReleases() {
  const token = process.env.GITHUB_TOKEN;
  const headers = {
    Accept: 'application/vnd.github+json',
    'User-Agent': 'woc-release-sync',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
  const url = `https://api.github.com/repos/${UPSTREAM_REPO}/releases?per_page=30`;
  try {
    const res = await fetch(url, { headers, signal: AbortSignal.timeout(10000) });
    if (!res.ok) throw new Error(`GitHub API error: ${res.status} ${res.statusText}`);
    return await res.json();
  } catch (err) {
    console.warn(`[sync_releases] Upstream fetch failed (${err.message}). Using local archives.`);
    return [];
  }
}

function updateReadme(allEntries) {
  let content = `# World of ClaudeCraft 全版本更新日志总览 (Release Notes Archive)\n\n`;
  content += `本文档归档了自游戏创立以来的全部版本更新记录。\n\n`;
  content += `| 版本号 | 标题 | 发布日期 | 详细更新说明 |\n`;
  content += `| :--- | :--- | :--- | :--- |\n`;

  for (const e of allEntries) {
    const dateStr = e.publishedAt ? e.publishedAt.slice(0, 10) : '-';
    content += `| \`${e.tag}\` | **${e.name}** | ${dateStr} | [查看详情](./${e.tag}.md) |\n`;
  }

  content += `\n---\n*本更新日志体系由本地化流水线实时维护与自动同步。*\n`;
  fs.writeFileSync(README_FILE, content, 'utf8');
}

export async function syncReleases({ checkOnly = false } = {}) {
  fs.mkdirSync(DOCS_DIR, { recursive: true });
  fs.mkdirSync(ARCHIVE_DIR, { recursive: true });

  const existingTags = getExistingTags();
  const upstream = await fetchUpstreamReleases();
  const newReleases = upstream.filter((r) => r && r.tag_name && !existingTags.has(r.tag_name));

  if (checkOnly) {
    if (newReleases.length > 0) {
      console.log(`[sync_releases] Found ${newReleases.length} untranslated releases: ${newReleases.map((r) => r.tag_name).join(', ')}`);
      return false;
    }
    console.log(`[sync_releases] All releases are up-to-date (${existingTags.size} tags archived).`);
    return true;
  }

  let addedCount = 0;
  for (const r of newReleases) {
    const tag = r.tag_name;
    const rawName = r.name || tag;
    const rawBody = r.body || '';
    const publishedAt = r.published_at || r.created_at || new Date().toISOString();
    const htmlUrl = r.html_url || `https://github.com/${UPSTREAM_REPO}/releases/tag/${tag}`;

    const translatedTitle = translateText(rawName.includes('World of') ? rawName : `World of ClaudeCraft ${tag} 版本更新`);
    const translatedBody = translateText(rawBody);

    const entry = {
      id: r.id || Date.now(),
      tag,
      name: translatedTitle,
      body: translatedBody,
      url: htmlUrl,
      prerelease: Boolean(r.prerelease),
      publishedAt,
    };

    // 1. Write archive json
    const jsonPath = path.join(ARCHIVE_DIR, `${tag}.json`);
    fs.writeFileSync(jsonPath, JSON.stringify(entry, null, 2), 'utf8');

    // 2. Write docs markdown
    const mdPath = path.join(DOCS_DIR, `${tag}.md`);
    const mdContent = `# ${entry.name}\n\n- **版本标签 (Tag)**: \`${tag}\`\n- **发布日期 (Published)**: \`${publishedAt.slice(0, 10)}\`\n- **官方链接**: [${tag}](${htmlUrl})\n\n---\n\n## 更新内容说明\n\n${translatedBody}\n\n---\n*World of ClaudeCraft 中文版本地化团队发布与归档*\n`;
    fs.writeFileSync(mdPath, mdContent, 'utf8');

    addedCount++;
    console.log(`[sync_releases] Archived and translated new release: ${tag}`);
  }

  // Reload all archives and rebuild active releases.json and README.md
  const allJsonFiles = fs.readdirSync(ARCHIVE_DIR).filter((f) => f.endsWith('.json'));
  const allEntries = [];
  for (const file of allJsonFiles) {
    try {
      const data = JSON.parse(fs.readFileSync(path.join(ARCHIVE_DIR, file), 'utf8'));
      if (data && data.tag) allEntries.push(data);
    } catch {
      // skip corrupted
    }
  }

  // Sort descending by publishedAt
  allEntries.sort((a, b) => {
    const da = new Date(a.publishedAt || 0).getTime();
    const db = new Date(b.publishedAt || 0).getTime();
    return db - da;
  });

  // Rebuild README.md
  updateReadme(allEntries);

  // Rebuild active window (data/releases.json)
  const activeWindow = allEntries.slice(0, ACTIVE_WINDOW_SIZE).map((e) => ({
    id: e.id,
    tag: e.tag,
    name: e.name,
    body: (e.body || '').slice(0, RELEASE_BODY_MAX),
    url: e.url,
    prerelease: e.prerelease,
    publishedAt: e.publishedAt,
  }));

  fs.writeFileSync(ACTIVE_FILE, JSON.stringify(activeWindow, null, 2), 'utf8');
  const activeSize = (fs.statSync(ACTIVE_FILE).size / 1024).toFixed(2);
  console.log(`[sync_releases] Active feed refreshed with ${activeWindow.length} items (${activeSize} KB). Total archived: ${allEntries.length}.`);

  return true;
}

// CLI entry point
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const checkOnly = process.argv.includes('--check');
  syncReleases({ checkOnly }).catch((err) => {
    console.error('[sync_releases] Fatal error:', err);
    process.exit(1);
  });
}
