---
name: woc-merge-upstream
description: "Workflow and best practices for fetching, merging, and resolving upstream World of ClaudeCraft releases into the release/china branch. Covers proxy acceleration, stash protection, conflict resolution with compliance guardrails, i18n alignment, test environment isolation, and full-gate verification."
---

# Merge Upstream Releases (WoC China Branch)

This skill documents the end-to-end standard operating procedure for integrating upstream
(`levy-street/world-of-claudecraft`) changes into the localized domestic branch (`release/china`),
preserving domestic regulatory compliance and avoiding regressions.

## 1. Network & Proxy Configuration

In WSL/Linux environments, direct connections to GitHub can hang or timeout.
Always invoke git fetch using the local host proxy:

```bash
# Verify proxy reachability (typically 127.0.0.1:7890 or 10808 on the host)
curl -I -s --connect-timeout 2 -x http://127.0.0.1:7890 https://www.google.com

# Fetch upstream with explicit proxy environment variables
http_proxy=http://127.0.0.1:7890 https_proxy=http://127.0.0.1:7890 git fetch upstream
```

## 2. Working Tree & Bot Stash Protection

The domestic development environment frequently contains active bot scripts or untracked
macro models in `python/`. Before initiating a merge:

1. Check repository status:
   ```bash
   git status
   ```
2. Stash unstaged/untracked modifications safely:
   ```bash
   git stash push -u -m "wip-bot-changes"
   ```
3. Never force-checkout or overwrite user-modified python files during git operations.

## 3. Merging & Conflict Resolution Rules

Initiate merge from the upstream branch (e.g. `upstream/main` or specific release tags):
```bash
git merge upstream/main
```

### Core Conflict Policies for China Branch:

1. **HTML Shells (`index.html` & `play.html`)**:
   - **Compliance Card Retention**: Retain the CADPA 12+ age badge, national health game advisory, ICP footer, and community non-commercial notice.
   - **Download Matrix**: Retain the custom desktop (Win/Linux/macOS) and mobile (Android/iOS) download grid pointing to domestic distribution URLs (`worldofclaudecraft.aoruantech.com`).
   - **Version Number**: Update `#game-version` and client links to match upstream's new version (e.g., `v0.43.2`).
   - **Language & Graphics Settings**: Retain the Chinese-first language selector and graphics control dropdowns.

2. **Localization & Translations (`src/ui/i18n.*`)**:
   - **Strict Upstream Alignment**: All in-game text, spell descriptions, mechanics notes, and lore follow upstream's `zh_CN.ts` exactly. Never alter or inject custom wording unless explicitly required for statutory compliance (e.g. anti-gambling, token regulation).
   - **Voice/Audio Asset Independence**: Upstream lacks Chinese voice packs; domestic voiceovers and custom sound manifests are maintained independently in the domestic branch.
   - **Cryptocurrency Isolation**: The $WOC Exchange (`#woc-market-window`, `#mm-wocmarket`) is hidden for compliance. Do NOT touch or confuse it with the normal in-game gold Market (`#market-window`), which must remain 100% intact and functional.

3. **Test vs Production Environment Language Isolation (`src/ui/i18n.ts`)**:
   - To prevent upstream unit tests from failing due to localized assertions (e.g. expecting "Enchanting" instead of "附魔"):
     ```typescript
     const isTestEnv =
       (typeof process !== 'undefined' && (process.env?.VITEST === 'true' || process.env?.NODE_ENV === 'test')) ||
       (typeof import.meta !== 'undefined' && Boolean(import.meta.env?.MODE === 'test'));
     export const DEFAULT_LANGUAGE: SupportedLanguage = isTestEnv ? 'en' : 'zh_CN';
     ```
   - This ensures browser/production clients default to `zh_CN`, while automated Vitest runs evaluate in `en`.

## 4. Verification Pipeline

After resolving conflicts and committing the merge:

1. **Type Checking**:
   ```bash
   export PATH=/home/yeleo/miniconda3/envs/claudecraft/bin:/usr/bin:/bin:$PATH
   npm run check:types
   ```
   Must pass with 0 errors across TS, Svelte, and Bot schemas.

2. **Catalog & Dictionary Generation**:
   ```bash
   npm run i18n:gen
   ```
   Regenerates resolved dictionaries across all 21 locales and verifies pending keys.

3. **Targeted & Parity Tests**:
   ```bash
   npx vitest run tests/char_window.test.ts tests/market_window.test.ts
   # Run tests for specific systems touched in the upstream update
   ```

4. **Production Bundle Verification**:
   ```bash
   npm run build
   ```
   Ensures bundle compilation, backdrop filter preservation, and media manifest generation succeed.

## 5. Post-Merge Restoration

Once all checks and tests pass:
1. Restore previously stashed bot changes:
   ```bash
   git stash pop
   ```
2. Verify tree status and confirm with the user before pushing to `origin/release/china`.

## 6. Release Notes & User Presentation Protocol (发版日志与用户直接交付规范)

每次完成上游合并（或版本热修复发布）后，**严禁仅在仓库中生成文件或只提供链接简写**，必须严格执行以下两项标准：

### 1. 同步维护发版“三件套”文件
必须创建或更新以下三个核心文件并提交至仓库：
1. **详细版本日志文档** (`docs/releases/vX.Y.Z-cn.md`)：
   - 包含版本标签、发布日期、Release 链接；
   - 包含核心亮点速览（分点说明本次修复的关键痛点与机制变动）；
   - 包含详细更新清单（按系统分类，如拍卖行与经济、副本与战斗、界面交互、国内合规分发等）。
2. **文档索引总表** (`docs/releases/README.md`)：
   - 在版本表格顶部按倒序追加最新版本行（版本号、更新主题、发布日期与对应文档超链接）。
3. **版本元数据注册表** (`data/releases.json`)：
   - 在 JSON 数组最前部插入最新版本对象（`version`, `title`, `date`, `path`, `features` 等），供游戏客户端、官网及启动器自动解析展示。

### 2. 交互回复中必须直接完整提供升级日志正文 (Mandatory In-Chat Delivery)
- **硬性要求**：任务完成向用户交付时，**必须在对话消息中直接逐字输出该版本的完整升级日志 Markdown 内容**。
- **禁止行为**：严禁仅回复“已更新日志，请查看 docs/releases/...”、“更新内容如下：修复了若干 Bug”等敷衍或简写形式。
- **目的**：方便用户无需进入代码仓库翻找即可秒级审阅全部改动、确认合规细节，并直接一键复制同步至游戏官网公告、QQ/微信玩家群或社区发行渠道。
