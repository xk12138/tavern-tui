# Tavern · 酒馆

A CLI-native, LLM-driven immersive interactive narrative engine.

一个命令行原生、由大模型驱动的沉浸式互动叙事引擎。推开酒馆的门,故事开始。

## 快速开始

```bash
# 用 uv(推荐)
uv tool install tavern-tui

# 或从源码 / GitHub 安装
uv tool install git+https://github.com/xk12138/tavern-tui.git

# 启动
tavern
```

首次启动会引导你:
1. 选一个 LLM provider,填 API key
2. 加载或创建一个世界
3. 创建你的角色

## 文档

- [`USAGE.md`](USAGE.md) — 安装、配置、开始第一段故事
- [`WORLD_BUILDING.md`](WORLD_BUILDING.md) — 怎么造一个自己的世界
- [`DESIGN.md`](DESIGN.md) — 引擎的架构与设计

## License

MIT — see [`LICENSE`](LICENSE).
