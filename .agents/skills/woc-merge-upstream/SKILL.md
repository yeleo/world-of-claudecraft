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
