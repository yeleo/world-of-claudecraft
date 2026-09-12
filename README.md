<div align="center">

# World of ClaudeCraft (中国特供 / 汉化与合规发布版)

**在浏览器中免费畅玩纯手工打造的经典时代 MMO：任务、组队、地下城与团队副本。**  
**基于官方 [levy-street/world-of-claudecraft](https://github.com/levy-street/world-of-claudecraft) 深度优化定制，全面适配国内网络环境与游玩体验。**

**官方中文网站：[https://worldofclaudecraft.aoruantech.com/](https://worldofclaudecraft.aoruantech.com/)**

[![Branch: release/china](https://img.shields.io/badge/branch-release%2Fchina-orange?logo=git)](https://github.com/yeleo/world-of-claudecraft/tree/release/china)
[![TypeScript](https://img.shields.io/badge/TypeScript-7.0-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Three.js](https://img.shields.io/badge/Three.js-r185-000000?logo=threedotjs&logoColor=white)](https://threejs.org/)
[![Vite](https://img.shields.io/badge/Vite-8-646CFF?logo=vite&logoColor=white)](https://vite.dev/)
[![Vitest](https://img.shields.io/badge/Vitest-4.1-6E9F18?logo=vitest&logoColor=white)](https://vitest.dev/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

[English (Upstream)](https://github.com/levy-street/world-of-claudecraft) · **简体中文 (本分支)** · [繁體中文](docs/i18n/README.zh_TW.md)

[特色与国内定制](#-核心特色与国内定制优化) · [分支管理机制](#-分支管理与上游同步机制) · [客户端下载](#-客户端支持)

![World of ClaudeCraft 游戏画面](docs/screenshots/title-screen.jpg)

</div>

---

## 🌟 核心特色与国内定制优化

本分支（`release/china`）作为专门面向中文玩家与国内私有化部署的发布版本，在完整保留上游所有战斗机制、副本、专业技能与数值系统的基础上，进行了全方位的深度优化：

### 1. 🇨🇳 13,400+ 词条全量精修汉化（100% 词条覆盖）
- 界面文本、任务剧情、Boss 技能机制、装备掉落、专业配方、成就系统等共计 **13,476** 条词条全面采用魔兽世界经典“信·达·雅”风格精心打磨。
- 默认语言强制优先设置为**简体中文（`zh_CN`）**，进入游戏即可零门槛畅玩。
- 补全双专业系统（Professions 2.0）10 个高阶专精衔称（爆破师、药剂师、捕兽人、制装师、织墨师、秘法师、缚晶师、铸刃师、铁匠、齿轮匠）。

### 2. ⚡ 国内网络加速与境外依赖脱钩
- **剔除 Cloudflare Turnstile 验证**：移除海外 Cloudflare 阻断脚本，杜绝国内网络由于无法加载验证脚本导致的白屏、请求挂起或登录失败。
- **本地字体与脱敏**：停用 Google Fonts 远程字体加载，优化中文字体渲染栈（优先回落至微软雅黑、PingFang SC 等系统原生优质无衬线体），避免外部 CDN 延迟。
- **分析工具受控**：屏蔽海外 Google Analytics 上报，保护玩家数据隐私。
- **分发镜像链路加速**：重构桌面客户端及 APK 下载直链，支持国内高速镜像代理，下载告别 404 与限速。

### 3. 🛡️ 合规与安全增强
- **聊天安全过滤系统**：内置敏感词过滤引擎，为社区交流与私服生态提供合规保障。
- **健康游戏忠告**：根据国内游戏发布标准，规范展示健康游戏忠告与未成年人保护指引。

### 4. 🎙️ 中文剧情语音（TTS）离线增强
- 内置针对 NPC 剧情对话、任务引导的中文语音离线生成与缓存体系，为纯代码渲染世界带来沉浸式的中配音画体验。



---

## 🌿 分支管理与上游同步机制

为了兼顾“紧跟官方最新特性”与“维护国内定制稳定性”，本仓库实行清晰的分支策略：

| 分支名 | 定位 | 说明 |
| :--- | :--- | :--- |
| **`release/china`** | **默认分支** (Default) | 国内发行版主分支。集成完整汉化包、合规优化、国内分发加速。所有生产发布均从此分支打 Tag。 |
| **`main`** | **上游镜像分支** | 100% 纯净镜像源仓库 `levy-street/world-of-claudecraft:main`。 |

- 仓库配置了定时自动化工作流（`.github/workflows/sync-upstream.yml`），每小时自动同步原作者仓库的最新提交至 `main` 分支。
- 绝不会直接将上游强制合并至 `release/china`，保证线上环境稳定可靠。

---

## 📱 客户端支持

除了现代 Web 浏览器直接即开即玩外，还支持打包为跨平台独立客户端：
- **Windows (x64 / ARM64)**: 独立桌面客户端
- **Linux (AppImage / deb)**: 跨发行版支持
- **Android**: 支持触屏操作布局的移动端客户端
