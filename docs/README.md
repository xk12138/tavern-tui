# docs · 项目文档索引

顶层的三份文档面向不同读者(装机 / 造世界 / 引擎架构),放在项目根目录:

- 📖 `../USAGE.md` —— 玩家侧使用手册
- 🌍 `../WORLD_BUILDING.md` —— 世界作者手册
- 🏗️ `../DESIGN.md` —— 引擎设计与里程碑

本目录 `docs/` 存放**过程性文档**:PRD、CHANGELOG、缺口分析、迁移说明等,随代码演进而增长。

---

## 目录索引

### 变更记录

- [CHANGELOG.md](./CHANGELOG.md) —— 版本变更历史

### 产品需求文档(PRD)

- [PRD-worldpack-validate.md](./PRD-worldpack-validate.md) —— `tavern validate` 世界包校验(v0.1.0 交付)
- [PRD-worldpack-install.md](./PRD-worldpack-install.md) —— `tavern install/list/uninstall` 世界包安装(v0.2.0 交付)
- [PRD-config.md](./PRD-config.md) —— `tavern config init/show/check/path` LLM 配置管理(v0.3.0 交付)
- [PRD-llm-provider-and-play.md](./PRD-llm-provider-and-play.md) —— LLM Provider 抽象层 + `tavern play` REPL(v0.4.0 交付)
- [PRD-save-scene-log.md](./PRD-save-scene-log.md) —— SQLite 存档 + 场景日志 + `/save` `/load` `/rewind`(v0.5.0 交付)
- [PRD-more-providers.md](./PRD-more-providers.md) —— OpenAI / DeepSeek / Ollama / Custom Provider 实现(v0.6.0 交付)
- [PRD-export-novel.md](./PRD-export-novel.md) —— `/export novel` 小说导出(v0.7.0 交付)
- [PRD-input-prefixes-and-observe.md](./PRD-input-prefixes-and-observe.md) —— 输入前缀语法 + `/where /who /inv /status /relations` 观察指令(v0.8.0 交付)

### 分析文档

- [gap-analysis-2026-08-11.md](./gap-analysis-2026-08-11.md) —— 项目功能缺口分析,从三种用户视角审视文档承诺与代码现状的差距

---

## 命名规范

- `PRD-<slug>.md` —— 产品需求文档
- `gap-analysis-<YYYY-MM-DD>.md` —— 缺口 / 现状分析
- `RFC-<slug>.md` —— 有争议的设计提案(需要讨论)
- `ADR-<NNN>-<slug>.md` —— 已决策的架构记录(不可变)
- `migration-<from>-to-<to>.md` —— 破坏性变更迁移指南

## 编写风格

- 中文为主,专有名词保留英文
- Markdown,不追求华丽格式
- 每份文档开头写清:**面向谁 / 什么状态 / 什么时间**
- 决策类文档一旦达成共识就冻结,后续变更另开一份
