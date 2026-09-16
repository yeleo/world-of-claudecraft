# World of ClaudeCraft (国内发行版) - 跟随上游主分支演进与冲突解决章程

## 1. 宗旨与分支架构

为了既能**持续享受上游开源社区（`levy-street/world-of-claudecraft`）的核心玩法迭代、数值平衡与引擎优化**，又能**稳固保障国内发行版的合规性、稳定性与专属服务配置**，特制定本演进与合并章程。

### 分支拓扑设计
```text
 upstream/main (开源官方原版主干)
      │
      │ (由 .github/workflows/sync-upstream.yml 每日全自动同步)
      ▼
 origin/main (本仓库保持与上游完全 1:1 的纯净快照镜像，不直接在其上做任何国内修改)
      │
      │ (当检测到更新后，通过 Issue 提醒人工按章程拉取演练分支合并)
      ▼
 sync/upstream-YYYYMMDD (临时演练分支，在此解决冲突并完成回归测试)
      │
      │ (Pull Request 经审查后合入)
      ▼
 origin/release/china (国内定制正式生产分支，部署国内服务器与发布安装包)
```

---

## 2. 资产保护白名单（“红线资产”，合并冲突时永远以国内版为准）

在任何向上游同步的过程中，遇到以下文件冲突时，**必须保留国内版本（使用 `--ours`）**，严禁被上游海外代码覆盖：

| 资产类型 | 涉及核心文件 | 保护原则与要求 |
| :--- | :--- | :--- |
| **法律与合规页面** | `public/terms.html`<br>`public/privacy.html`<br>`public/data-deletion.html`<br>`public/links.html` | 必须为纯中文合规文案，涵盖 CADPA 12+ 适龄提示、ICP 备案号、数据删除与注销协议。 |
| **客户端分发与下载配置** | `src/game/desktop_download.ts`<br>`index.html`<br>`play.html` (下载区域) | 保持国内下载基址 (`DOWNLOAD_BASE`)，保持 Windows (x64/ARM64)、Linux (x86_64/ARM64) 与 Android APK 下载，保持 macOS (即将上线) 状态。 |
| **国内原生端与 API 映射** | `android/`<br>`capacitor.config.ts`<br>`.github/workflows/` (已重构的工作流) | `VITE_API_ORIGIN` 必须指向 `https://worldofclaudecraft.aoruantech.com`，禁用 Discord/海外钱包插件。 |
| **汉化覆盖表** | `src/ui/i18n.locales/zh_CN.ts`<br>`src/ui/i18n.catalog/` | 保持国内版 100% 汉化与专属润色。 |

---

## 3. 积极跟进上游的范围

遇到以下改动时，应积极采纳上游更新（使用 `--theirs` 或仔细人工比对）：
1. **游戏新特性与数值**：新副本、新职业天赋、新物品、技能数值平衡。
2. **底层引擎与性能优化**：WebGL/WebGPU 渲染批次优化、物理碰撞算法、内存泄漏修复。
3. **网络协议底层**：WebSocket 序列化改进、数据包压缩优化。
4. **安全加固**：依赖漏洞修补、防作弊检测逻辑增强。

---

## 4. 标准化同步与冲突解决 SOP (4 步操作法)

当 GitHub Actions 发出 `[Upstream Sync]` Issue 提醒，或计划主动跟进上游大版本时，请按以下步骤执行：

### 第一步：准备干净的工作区并拉取最新基线
```bash
# 切换到国内主分支并确保本地无未提交改动
git checkout release/china
git pull origin release/china

# 拉取最新同步好的 main 镜像
git fetch origin main
```

### 第二步：建立专用同步隔离演练分支
```bash
# 从当前的 release/china 切出日期演练分支
git checkout -b sync/upstream-$(date +%Y%m%d)
```

### 第三步：合并并一键化裁决红线资产冲突
```bash
# 触发合并
git merge origin/main
```
若提示存在冲突（CONFLICT）：
1. **一键还原所有国内红线资产（快速保平安）**：
   ```bash
   # 保护所有法律条款、隐私、数据注销及下载页面
   git checkout --ours public/terms.html public/privacy.html public/data-deletion.html public/links.html
   git checkout --ours index.html play.html
   git checkout --ours src/game/desktop_download.ts
   git checkout --ours src/ui/gpu_notice_view.ts
   git checkout --ours .github/workflows/
   ```
2. **处理游戏逻辑与代码冲突**：
   * 打开 IDE（如 VS Code / Antigravity），对 `src/game/`, `src/net/`, `server/` 等业务代码进行逐行审查。
   * 优先保留上游的功能补丁，同时保留国内版已做的中文字符集与网络配置。
3. **标记已解决**：
   ```bash
   git add -A
   git commit -m "chore(sync): merge upstream main changes with china localization safeguards"
   ```

### 第四步：本地全量自动化验证并提交 PR
在合并分支上执行质量门禁套件：
```bash
# 1. 验证类型检查（确保没有任何 TS 报错）
npm run check:types

# 2. 验证构建流程（确保打包正常）
npm run build
npm run build:server

# 3. 验证关键单测
npm test -- tests/desktop_download.test.ts tests/desktop_download_dom.test.ts
```
所有检查通过后：
```bash
# 推送演练分支
git push origin sync/upstream-$(date +%Y%m%d)
```
在 GitHub 网页上发起 Pull Request: `sync/upstream-YYYYMMDD` -> `release/china`。CI 绿标后即可合并合入生产！

---

## 5. 协议与世界布局版本 (`ONLINE_WORLD_LAYOUT_VERSION`) 演进与仲裁规则

`ONLINE_WORLD_LAYOUT_VERSION`（位于 `src/world_api.ts`）是客户端与服务端在 WebSocket 握手阶段（`auth-world-XX`）的核心 Epoch 判决标识。当且仅当客户端和服务端的版本完全一致时才允许连入，否则立即熔断断开并弹窗提示客户端升级。

在后续跟随上游主干同步时，针对该版本号的仲裁策略如下：

### 场景 1：上游发布常规版本（未变动世界布局，上游仍为 29）
* **原理**：上游常规功能、数值、UI 修复通常不修改 Epoch。
* **裁决**：**保持与上游基准一致（29）**。
* **原因**：国内已经全量分发并部署了基于 30 的客户端与服务端，不能倒退回 29，否则会导致已更新客户端不可用。

### 场景 2：上游也发布了破坏性世界更新，且上游也升级为 30
* **原理**：上游引入了新的地图/世界布局/金库协议破坏性变更，上游也使用了版本号 30，与国内版发生“同号碰撞”。
* **裁决**：**自增避让原则——国内版直接顺延递增为 31**。
* **操作**：
  1. 在演练分支中将 `ONLINE_WORLD_LAYOUT_VERSION` 改为 `31`；
  2. 重新生成并运行单测 `npm test`；
  3. 合并上线后，同步更新国内服务端，并发布 v31 对应的客户端安装包。
* **效果**：完美吸收上游的最新世界改动，且国内老客户端平滑收到强制升级通知。

### 场景 3：上游大版本跨越（如上游升级为 31 或更高）
* **原理**：上游的 Epoch 已经自然高于国内版。
* **裁决**：**取最大值原则——直接采纳上游更高版本（如 31/32）**。
* **原因**：更高的 Epoch 会直接使所有旧客户端失效，自然驱动用户更新至最新版。

> [!TIP]
> **日常最佳实践**：未来在正常发版节奏中（不限制“版本号不变”时），优先通过 `package.json` 的标准语义化版本（如 `0.42.3`、`0.43.0`）进行常规功能迭代；只有在需要物理切断老旧客户端进服通道、或地图数据结构重大重构时，才自增 `ONLINE_WORLD_LAYOUT_VERSION`。

