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

## 4. Bidirectional Change Audit (双向变更审查：正向变动梳理 + 反向本地化防回归审查)

在代码合并解决冲突后、进入自动化测试验证前，**必须执行严格的“双向变更审查”**，杜绝潜在隐式 Bug：

### 1. 正向变更审查 (Upstream Forward Audit - 逐项剖析上游变动)
梳理上游从上一个合并基准（Base Tag/Commit）到本次目标版本的所有改动点，明确上游改了什么：
```bash
# 1. 查找上一个合并基准点或 Tag
BASE_COMMIT=$(git merge-base HEAD upstream/main)

# 2. 输出上游全部变更 Commits 清单
git log --oneline --no-merges ${BASE_COMMIT}..upstream/main

# 3. 查看变动涉及的目录与文件统计
git diff --stat ${BASE_COMMIT}..upstream/main
```
**审查重点与影响面排查**：
- **协议与数据契约 (Wire Format & Protocols)**：检查 `headless/`、`src/sim/obs.ts`、WebSocket 消息类型是否变动。若协议变更，必须同步镜像检查 Python RL 绑定与 Bot 宏观控制脚本。
- **UI 架构与生命周期 (DOM / HUD / Svelte)**：检查上游是否重构了弹窗管理器、HUD 布局、事件监听器，识别哪些变动碰到了国内定制的挂载点。
- **经济与任务逻辑 (Economy & Quests)**：检查任务触发链条、物品 ID、NPC 刷新坐标的变动，标记新增或重写的任务剧情。
- **存储与状态 (State & Storage)**：检查 LocalStorage、IndexedDB 或角色存档 Schema 是否发生向下不兼容迁移。

### 2. 反向影响审查 (Localization Backward Audit - 本地化反向代入防回归)
将国内分支的所有特有定制与合规模块，反向代入新合并的代码树中进行二次审视，严防“上游看似正常的改动”与“本地定制”碰撞产生新 Bug：

1. **合规隔离防泄漏审查 (Compliance Guardrail Integrity)**：
   - 上游新提交是否在新的界面（如设置面板、新手引导、状态栏）中增加了对 `$WOC`、加密货币钱包或 Web3 的隐式调用？
   - 反向验证：国内分支对 `#woc-market-window`、`#mm-wocmarket` 的屏蔽是否彻底无遗漏；同时确保正常的纯游戏金币市场（`#market-window`）功能未受附带损伤。
2. **UI 容器与 DOM 结构稳定性审查 (DOM Stability)**：
   - 检查上游对 `index.html` / `play.html` 的结构重构是否会冲刷或挤压国内定制元素（CADPA 12+ 适龄提示、国家健康游戏忠告、ICP 备案号、国内全平台下载网格）。
   - 检查 CSS 层叠与 Z-index：确保国内版弹窗与悬浮层在新的 HUD 层级下没有被遮挡或阻断鼠标指针。
3. **环境语言隔离防回归审查 (Language Isolation)**：
   - 确认 `src/ui/i18n.ts` 中的环境隔离逻辑依然完备：
     浏览器端/生产环境强制默认 `zh_CN`；Automated Test (`vitest`) 强制锁定 `en`，防止上游新增的单元测试因中文断言直接暴碎。
4. **离线配音与音画一致性联动 (Voice Alignment)**：
   - 若上游对白发生增删改，必须联动执行第 6 节的离线配音门禁，保证字幕与配音 100% 对应，杜绝“字幕显示新版，配音读旧版”。
5. **Bot 与多智能体兼容性反向验证 (Bot Protocol Check)**：
   - 若上游触碰底层物理或空间动作，反向拉起快速 smoke test（如 `python example_random_agent.py`），确认无未知反序列化报错。

## 5. Verification Pipeline

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

## 6. Offline TTS & Voice Line Synchronicity (强制离线配音与文本变更检查)

每次完成上游代码合并（尤其是涉及 `src/ui/i18n.locales/` 与任务剧情文本变动）后，**必须强制执行离线配音一致性门禁检查**。

### 1. 架构革新：角色声纹资产与业务台词物理解耦 (Decoupled Voice Anchor Architecture)
为根治“上游打招呼文案变动导致 NPC 音色突变、连带全量重算”的系统性隐患，配音系统实行**角色声纹资产 (Anchor) 与游戏业务台词 (Dialogue) 的物理解耦架构**：

$$\text{全新 NPC} \xrightarrow{\text{VoiceDesign 抽卡}} \text{固化永久声纹母本 (scripts/voices/anchors/)} \xrightarrow{\text{VoiceClone(decouple=True)}} \text{全量业务台词 (Greeting / Quest / Yell)}$$

1. **核心痛点与认知**：
   - 过去把游戏打招呼（Greeting）直接当母本，只要上游或本地化润色修改了 Greeting 的文字，就会被迫重新调用 VoiceDesign（随机采样），导致 NPC 音色彻底突变，玩家听觉认知锚点崩塌；且该 NPC 下辖的数十条任务台词会被迫连带重绘。
2. **声纹资产库化 (`scripts/voices/anchors/`)**：
   - 每个 NPC 拥有专属、独立且永久冻结的音频母本 `scripts/voices/anchors/<npc_id>.mp3` 及其元数据 `anchor_manifest.json`。
   - 声纹母本是角色的数字声学 DNA，**永远不随游戏业务文本变动而变动**。
3. **业务台词 100% 受体化 (含 Greeting)**：
   - 游戏内所有台词（包括 Greeting、Quest Offer/Complete、Yell），全部被视为受体台词。
   - 所有台词统一以 `scripts/voices/anchors/<npc_id>.mp3` 为基准母本，执行 **`VoiceClone(decouple=True)` 纯声纹解耦克隆**。
4. **零扩散增量更新**：
   - 当上游合并修改了某 NPC 的 Greeting 或任务对白时，**母本完全不动**，系统仅对变动的那一句台词执行单条解耦克隆。
   - **音色绝对稳定**（100% 继承母本 x-vector），且**绝无连锁重绘**！
5. **VoiceDesign 的唯一准入场景**：
   - 仅当游戏引入了**数据库从未收录过的全新 NPC** 时，才使用 VoiceDesign 抽卡调试出最佳音色，固化写入 `scripts/voices/anchors/`，此后永久转入解耦克隆模式。

### 2. 强制变更扫描与指纹校验
执行增量状态检查命令：
```bash
conda activate tts
python scripts/gen_chinese_voices.py --status
```
该命令会自动比对 `src/ui/i18n.locales/zh_CN.ts` 最新台词与 `scripts/voices/zh_voice_cache.json` 中的配置指纹（MD5/SHA256）。
- 若提示 `✨ 所有语音均已处于最新状态`：表示全部 578 条语音与文本 100% 同步，无需重新生成。
- 若提示 `待生成/待更新: N 条`：表明上游合并修改了剧情文本或问候语，只需执行自动化增量重绘。

### 3. 文本规整与变量插值防崩规范
合成前必须经过 `clean_spoken_text()` 规整：
- 变量替换：`{playerName}`、`{className}` 等占位符统一替换为自然的朗读称谓「冒险者」。
- 标点净化：严禁产生 `，。`、`，，` 等冲突重叠标点，杜绝 TTS 模型因标点异常引发的卡顿与高频破音。

### 4. 自动化增量重绘与母本固化执行指令
当扫描发现存在变动条目时，执行自动化增量重绘：
```bash
# 1. 确保本地 TTS 服务已启动 (http://127.0.0.1:7860)
# 若未启动，可执行: cd ~/src/tts && bash start.sh

# 2. 执行自动化增量合成 (读取 anchors/ 声纹母本，以 VoiceClone decouple=True 生成)
conda activate tts
python scripts/gen_chinese_voices.py

# 3. (可选) 如有新 NPC 引入或需重建基准母本库，可执行母本资产固化快照：
python scripts/snapshot_voice_anchors.py
```
- **自动清单同步**：脚本执行完毕后会自动根据实际生成的 MP3 物理文件哈希更新 `src/game/voice_manifest.zh_CN.generated.ts`，并写入 `scripts/voices/zh_voice_cache.json`。
- **验证与提交**：执行 `npm run check:types` 确认无报错后，将变动的音频文件、母本库、缓存及 Manifest 统一提交至分支。

## 7. Post-Merge Restoration

Once all checks and tests pass:
1. Restore previously stashed bot changes:
   ```bash
   git stash pop
   ```
2. Verify tree status and confirm with the user before pushing to `origin/release/china`.

## 8. Release Notes & User Presentation Protocol (发版日志与用户直接交付规范)

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
