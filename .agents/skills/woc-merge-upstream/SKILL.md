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

## 5. Offline TTS & Voice Line Synchronicity (强制离线配音与文本变更检查)

每次完成上游代码合并（尤其是涉及 `src/ui/i18n.locales/` 与任务剧情文本变动）后，**必须强制执行离线配音一致性门禁检查**。

### 1. 强制变更扫描与指纹校验
执行增量状态检查命令：
```bash
conda activate tts
python scripts/gen_chinese_voices.py --status
```
该命令会自动比对 `src/ui/i18n.locales/zh_CN.ts` 当前最新台词与 `scripts/voices/zh_voice_cache.json` 中的配置指纹（MD5/SHA256）。
- 若提示 `✨ 所有语音均已处于最新状态`：表示全部 578 条语音与文本 100% 同步，无需重新生成。
- 若提示 `待生成/待更新: N 条`：表明上游合并修改了任务文本或 NPC 问候语，必须对变更条目进行同步重绘。

### 2. 标准 TTS 角色配音工作流规范 (VoiceDesign 抽卡 -> 固化母本 -> VoiceClone 解耦锁定)
为了保证同一 NPC 在游戏内与玩家交互时（打招呼 Greeting、任务承接 Offer、任务交付 Complete）音色绝对统一，严禁直接对不同台词滥用 VoiceDesign 跨文本直接合成。必须严格执行三步法标准规范：

$$\text{VoiceDesign (设计抽卡)} \longrightarrow \text{固化为音色锚点 (Anchor)} \longrightarrow \text{VoiceClone (情感解耦锁定)}$$

1. **第一步：VoiceDesign 抽卡 (设计基准音色)**
   - 在 `qwen_design` 模式下，输入角色专属设定提示词（`NPC_VOICE_INSTRUCTS`），为角色代表性问候语（Greeting）生成候选音频。
   - **底层认知**：Prompt 描述词只是概率分布，自回归解码序列会随不同文本发散，固定 Seed 无法跨台词锁定音色。因此需通过抽卡选出一句发音饱满、语调自然、无爆音/变调失真的高分母本。
2. **第二步：固化角色音色锚点 (Anchor Audio)**
   - 将抽卡合格的音频保存并固化为该 NPC 的基准母本文件：
     `public/audio/voice_zh/<voice_npc>/greeting__<npcId>.mp3`
   - 验证音频声学质量：使用声学分析脚本检查基频（F0），确认无异常高频尖叫或假音跳变（如老年/中年男声中突现 >350Hz 破音）。
3. **第三步：VoiceClone 批量合成所有台词 (情感解耦锁定)**
   - 该角色所有任务、剧情及衍生台词，100% 切换至 `qwen_clone` 模式。
   - 以第二步固化的基准音频为参考源，**强制开启情感解耦模式 (`decouple=True`，即 `x_vector_only_mode=True`)**。
   - **效果保证**：参考音频死锁全局声纹向量（x-vector），而情感解耦避免新剧情台词的情绪被参考音频带跑，实现音色 100% 统一稳定，且台词情感自然演变。

### 3. 文本规整与变量插值防崩规范
合成前必须经过 `clean_spoken_text()` 规整：
- 变量替换：`{playerName}`、`{className}` 等占位符统一替换为自然的朗读称谓「冒险者」。
- 标点净化：严禁产生 `，。`、`，，` 等冲突重叠标点，杜绝 TTS 模型因标点异常引发的卡顿与高频破音。

## 6. Post-Merge Restoration

Once all checks and tests pass:
1. Restore previously stashed bot changes:
   ```bash
   git stash pop
   ```
2. Verify tree status and confirm with the user before pushing to `origin/release/china`.

## 7. Release Notes & User Presentation Protocol (发版日志与用户直接交付规范)

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
