# 酒馆 · 开发文档

> 这份文档面向**引擎开发者与项目贡献者**,讲清楚 Tavern 要做成什么样、为什么这么做、怎么落地。
>
> 想装起来玩:看 `USAGE.md`
> 想造一个世界:看 `WORLD_BUILDING.md`

---

## 一、愿景

**Tavern 是一个纯命令行的、由大模型驱动的、可以持续几十小时的沉浸式互动叙事引擎。**

用户先设定一个世界,再定义自己在这个世界中的角色,然后由大模型作为"故事总导演 + 所有 NPC",和用户共同演绎一段可持续演化的长篇故事。

### 参照物

- 老派 **MUD** —— 纯文字、终端、REPL 式交互
- **TRPG 跑团** —— 有 GM、有世界规则、玩家自由行动、后果被追踪
- **AI Dungeon / SillyTavern** —— LLM 扮演角色和世界

**Tavern 与它们的区别**:更强调**结构化的世界状态、长期一致性、可持续演化的剧情**,并且**内容与引擎彻底解耦** —— 引擎不带任何默认世界、任何默认 LLM,做纯粹的"叙事运行时"。

### 核心体验目标

- **世界可信**:设定不随对话漂移,NPC 有记忆、有立场、有目的
- **剧情有推进**:不是"陪聊",而是有节奏、有冲突、有转折的叙事流
- **选择有后果**:每一次决定都真实改变 NPC 态度、势力关系、世界状态。**死亡是真的死亡**
- **可以走很远**:不因上下文窗口爆掉而失忆,玩到十万字、几十小时仍然自洽
- **在哪都能玩**:一条命令启动,SSH / tmux / 树莓派上都能开局
- **完全开放**:内容无预设边界,题材/尺度由世界作者和玩家自行决定

### 项目形态

**开源项目**。核心引擎完全**题材中立、LLM 中立**,不预置任何世界、任何题材、任何 LLM 后端。所有内容通过**世界包**提供,LLM 由用户自选。生态由社区世界包驱动。

### "酒馆"作为入口的隐喻

"酒馆"不是随便取的名字,而是一条产品设计原则:

**酒馆是所有故事的最小共同起点。** 无论世界是什么题材,总能有一间"酒馆"—— 一个陌生人合理相遇、消息合理流通、任务合理接下的空间。它给玩家一个可预期的开局节奏:**推门 → 打量 → 遇到某个人 → 故事开始**。

落地为四件事:
1. 每个世界都有一个"**初始酒馆**"作为开局场景
2. `/tavern` 指令可以随时"回酒馆",作为软性锚点
3. 死亡后可以选择"回到酒馆"重生(见 §三 死亡机制)
4. 多世界共享一个 CLI 入口 —— 敲 `tavern`,先看到的是"元酒馆"式的世界选择器

---

## 二、系统架构

```
┌────────────────────────────────────────────────────┐
│              终端交互层 (TUI · Textual)             │
│   叙事流 · 状态条 · 输入行 · `/` 系统指令           │
└─────────────────────┬──────────────────────────────┘
                      │
┌─────────────────────▼──────────────────────────────┐
│            叙事编排层 (Orchestrator)                │
│  · 输入分派:自由文本 / 系统指令 / 快捷动作          │
│  · 调度 4 个 LLM 角色                                │
│  · 应用 state_delta、触发死亡分支、场景摘要         │
└──────┬──────────────────────────────┬──────────────┘
       │                              │
┌──────▼───────────┐            ┌─────▼──────────────┐
│  LLM 调用层       │            │   状态存储层        │
│                  │            │                    │
│  ● Narrator ────┐│            │ · 世界设定(静态)   │
│  ● Extractor    ││◄──上下文───┤ · 世界状态(动态)   │
│  ● Director     ││            │ · 长期记忆(向量库) │
│  ● MemoryKeeper─┘│──写入摘要─►│ · 场景日志(原文)   │
│                  │            │                    │
└──────────────────┘            └────────────────────┘
```

### 四个 LLM 角色

| 角色 | 出场频率 | 职责 | 玩家可见? |
|---|---|---|---|
| **Narrator** (叙事 GM) | 每回合 1 次 | 描写环境、扮演所有 NPC、推进剧情、判定行动后果 | 是,所有叙事文本 |
| **Extractor** (状态提取器) | 每回合 1 次 | 读 Narrator 输出 + 上下文,产出结构化 `state_delta` (JSON) | 否 |
| **Director** | 低频,**渐进介入**(见 §三) | 战略决策:该转折了吗? 该让谁登场? 主线该往哪推? | 否,只影响下一次 Narrator 的提示 |
| **Memory Keeper** | 场景结束 / 达到阈值 | 压缩对话为摘要、更新 NPC / 势力 / 地点的长期记忆 | 否 |

### 关键设计决定:Narrator + Extractor 分离

让 Narrator 专注创作、不被 JSON 尾巴干扰,叙事质量更好;Extractor 只做提取,可以流式并行 —— 玩家看到叙事文本时,后端同时提取状态。**双调用带来的成本翻倍是自觉的取舍**,为的是沉浸感。

M0 只实现 Narrator + Extractor,Director 和 Memory Keeper 后续里程碑逐步引入。

---

## 三、核心机制

### 3.1 属性系统:硬指标 + 软标签 + 关键检定

- **硬指标**(系统数值追踪):HP、精神值、金钱、时间
- **软标签**(自由文本,GM 参考):"擅长剑术"、"精通医术"、"名声不好"
- **关键检定**:日常互动 GM 自由裁量,关键行动(生死、剧情节点、超能力范围的尝试)才骰子

避免了纯 TRPG 事事骰子的僵硬,又保留了不可预测性。

### 3.2 死亡机制:硬死亡 + 双出口

HP 归零 = **game over**。GM 生成临终描写,弹出三个选项:

- **[R] 读档** —— 回到最近存档点
- **[T] 回到酒馆** —— 同世界同 PC(状态重置)重开一局。**上一次的死亡在这个世界里真实发生过**,可能作为传闻/回声在后续出现
- **[Q] 退出** —— 关掉,存档保留

`/rewind` 只能撤销手滑,**死亡后不可用**。没有廉价复活。

### 3.3 剧情渐进推进

Director 不从开局就掌控节奏,采用**三阶段介入**:

| 阶段 | 触发条件 | Director 行为 |
|---|---|---|
| **蜜月期** | 0 ~ N₁ 回合 | 完全不介入。玩家自由探索、认识 NPC、熟悉世界 |
| **轻推期** | N₁ ~ N₂ 回合 | 偶尔向 Narrator 建议"该有个转折了""该让 XX 出现" |
| **策划期** | N₂+ 回合 | 主动埋伏笔、推进主线、构造小高潮 |

阈值 N₁ / N₂ **由世界包配置**(默认 N₁=20, N₂=50)。Director 的输出是**导演笔记**,写给下一回合的 Narrator 看,不写给玩家。

### 3.4 无硬性通关

不设胜利条件。故事是否"完了"由 GM 判断 —— 主角死亡、大目标达成、玩家主动收尾,都算一次完整的旅程。

---

## 四、回合循环

```
1. 意图解析           输入是对话? 行动? 系统指令? 快捷动作?
                        ↓
2. 上下文组装         系统提示 (Narrator 人格 + 世界规则)
                    + 世界状态摘要
                    + 当前场景近期对话 (滑动窗口)
                    + 长期记忆检索的 top-k 相关片段
                    + 在场 NPC 的人物卡与关系值
                    + Director 上一次留下的"导演笔记"(如有)
                        ↓
3. Narrator 调用      (LLM 调用 #1)
   ┌─ 3a. 流式打印 ──────────┐   玩家立刻看到叙事
   │                          │
   └─ 3b. 全文完成后 ─────────┘
                        ↓
4. Extractor 调用     (LLM 调用 #2)
                      读 Narrator 全文 → 输出 JSON state_delta
                        ↓
5. 应用 state_delta   写入 world_state,推进时间轴
                        ↓
6. 死亡检查           HP ≤ 0?  是 → 死亡分支; 否 → 继续
                        ↓
7. Memory Keeper      场景边界 / 阈值触发时才调用
                        ↓
8. Director 判断      按渐进策略决定是否介入
                        ↓
9. 渲染状态变化       灰色分隔线报告 HP / 关系值 / 事件变化
```

关键节点:
- **第 3a 步就开始渲染** —— 玩家的等待感是"叙事完 = 回合完",Extractor 是幕后
- **第 6 步严格前置** —— HP 归零立刻切死亡分支,不再问 Director
- **原始 turn 日志无论走到哪都要保留** —— 小说导出功能依赖它

---

## 五、长期记忆:四层策略

上下文窗口是最大敌人。分层存取:

| 层 | 存什么 | 怎么用 |
|---|---|---|
| **L1 短期** | 当前场景的完整原文 | 直接塞进 prompt |
| **L2 场景摘要** | 每个已结束场景一段 ~200 字摘要 | 按时间倒序 / 相关性检索,取 top-k |
| **L3 实体长期记忆** | 每个 NPC / 势力 / 地点一段"发生过什么"| 场景相关实体的记忆自动挂载 |
| **L4 世界状态快照** | 结构化 KV | 每回合直接注入 |

**检索**:向量库(本地 embedding) + 关键词过滤 + 最近性权重。

**写入**:场景结束时由 Memory Keeper 生成摘要,并更新相关实体的记忆条目。避免让 Narrator 自己"顺便"写记忆,以免它偷懒复述原文。

**只读约束**:玩家**不能**手动编辑 NPC 记忆或世界状态。这是游戏,不是共创写作工具 —— NPC 记错了、记漏了,那就是它这个角色的一部分。

---

## 六、数据模型(实现草图)

```yaml
world:
  id: str
  name: str
  setting: {era, genre, tone, rules_summary}
  factions: [Faction]
  timeline: [KeyEvent]
  initial_tavern: SceneDef
  plot_pacing: {N1: int, N2: int}

player_character:
  name: str
  background: str
  hp: {current: int, max: int}          # 硬指标 · 归零即死
  attributes: {金钱: int, 精神: int, ...}
  attribute_tags: [str]                 # 软标签
  inventory: [Item]
  location: str
  relations: {npc_id: RelationScore}

npc:
  id: str
  name: str
  card: {personality, goals, secrets, speech_style}
  status: {location, health, mood, ...}
  memory_of_player: [str]               # 玩家不可编辑
  relation_to_player: {好感, 信任, 恐惧}

world_state:
  day: int
  time: str
  turn_count: int                       # Director 判断阶段用
  director_note: str                    # 上次 Director 留给 Narrator 的笔记
  active_events: [Event]
  faction_states: {faction_id: FactionState}

scene_log:
  scene_id: str
  turns: [{role, text, timestamp}]      # 原始日志,不压缩,供小说导出
  summary: str                          # 场景结束由 Memory Keeper 生成
  state_delta: dict
  outcome: enum {continued, ended, death}

death_record:                           # 死亡是世界的一部分,不删除
  character_name: str
  died_at: {day, time, location}
  cause: str
  final_scene_id: str
```

存档 = 一个 SQLite 文件,包含以上全部表 + 向量索引。

---

## 七、技术选型

| 层 | 选择 | 说明 |
|---|---|---|
| 语言 | Python 3.11+ | LLM SDK / 向量库生态最全 |
| TUI | **Textual** | 组件化、CSS、异步、Markdown,最接近 Claude Code 的交互形态 |
| LLM 适配 | 统一抽象层 | 可插拔:Anthropic / OpenAI / DeepSeek / Ollama / 任意 OpenAI 兼容接口 |
| 向量库 | `chromadb` 或 `sqlite-vss` | 单机嵌入式,零运维 |
| 存储 | SQLite | 单文件、跨平台、易备份 |
| 配置 | TOML | 世界包和用户配置统一格式 |
| 打包 | `uv tool install` / `pipx` | 一条命令装好 |
| 依赖管理 | `uv` | 现代 Python 首选 |

**项目形态**:一个 `tavern` CLI 命令 + `~/.config/tavern/` 目录(config + worlds + saves)。

### TUI 框架选择:为什么是 Textual

对比过三条路:

| 框架 | 特点 | 类比 | 适配度 |
|---|---|---|---|
| **Textual** | 组件化(类 React)、CSS、原生异步、`RichLog`/`Input`/`Markdown` widget | Claude Code (Ink) | ★★★★★ |
| `rich` + `prompt_toolkit` | 轻量但需自己搭"分区布局 + 状态同步" | pgcli / IPython | ★★★☆☆ |
| `curses` / `blessed` | 底层,完全手搓 | vim / htop | ★★☆☆☆ |

选 Textual 的理由:
1. Claude Code 用 Ink(TypeScript 的 React-terminal),Textual 是 Python 生态里最接近的形态
2. 内置 widget 直接映射到目标布局:`Input`=输入行、`RichLog`=叙事流、`Static` + reactive=状态条
3. 原生 `async/await`,无缝对接流式 LLM 输出实现打字机效果
4. Markdown 渲染开箱即用
5. `/` 斜杠命令自动补全 / 键盘绑定 / `Ctrl+P` 命令面板都能直接用
6. CSS 主题系统,后续用户可自定义配色

代价:比 `rich + prompt_toolkit` 依赖重、启动稍慢。可接受。

---

## 八、代码结构(规划)

```
tavern/
├── pyproject.toml
├── README.md
├── USAGE.md
├── WORLD_BUILDING.md
├── DESIGN.md
├── LICENSE
├── src/tavern/
│   ├── __init__.py
│   ├── cli.py              # tavern 命令入口
│   ├── config.py           # ~/.config/tavern 读写
│   ├── orchestrator.py     # 回合循环
│   ├── llm/
│   │   ├── base.py         # Provider 抽象
│   │   ├── anthropic.py
│   │   ├── openai.py
│   │   ├── deepseek.py
│   │   └── ollama.py
│   ├── roles/
│   │   ├── narrator.py     # 4 个 LLM 角色的 prompt 组装 + 调用
│   │   ├── extractor.py
│   │   ├── director.py
│   │   └── memory_keeper.py
│   ├── state/
│   │   ├── world.py        # 世界包加载
│   │   ├── save.py         # SQLite 存档
│   │   └── memory.py       # 向量记忆
│   ├── tui/
│   │   ├── app.py          # Textual 应用主体
│   │   ├── widgets.py
│   │   └── styles.tcss     # Textual CSS
│   └── worldpack/
│       ├── loader.py       # 世界包解析、验证
│       └── schema.py
├── tests/
└── examples/
    └── minimal-tavern/     # 最小测试世界包(仅供开发验证,非官方世界)
        └── world.toml
```

---

## 九、里程碑

### M0 · 骨架跑通(1 周)
- `pyproject.toml` + `uv` 项目骨架
- LLM provider 抽象层 + 至少一个 provider adapter(任选一个先跑通)
- 首次运行引导:填 API key、加载 `examples/minimal-tavern/` 测试世界包
- Narrator + Extractor 双调用循环,纯 stdin/stdout
- HP 归零 → 死亡分支([R] / [T] / [Q])
- **目标**:能在终端里玩 20 回合,能死一次

### M1 · 状态与记忆(2 周)
- 结构化 `world_state` + `scene_log`,持久化到 SQLite
- `~/.config/tavern/` 目录布局
- 场景摘要机制(Memory Keeper 独立)
- NPC 好感度追踪
- `/save` `/load` `/status` `/who` `/rewind` 等基础指令

### M2 · TUI 增强(2 周)
- 引入 Textual,做出目标三分区布局
- 底部输入行 + 顶/底状态条实时刷新
- Markdown 渲染 + 颜色编码 + 打字机流式输出
- `/` 斜杠命令 + 自动补全
- 死亡分支的仪式感 UI

### M3 · 长期记忆 + 渐进推进 + 小说导出(3 周)
- 向量检索接入
- 多场景切换
- NPC 独立长期记忆
- **Director 独立并落地"渐进推进"策略**
- `/export novel` —— 把 turn 日志重写为第三人称小说

### M4 · 开源发布 + 世界包生态(必做)
- 世界包 TOML 规范完整实现
- `tavern install <world-pkg>` / `tavern validate <path>`
- 官方或社区贡献几个示范世界包供用户下载(**不打包进引擎**)
- README / CONTRIBUTING / 世界包创作指南(见 `WORLD_BUILDING.md`)
- CI + 测试覆盖
- 发布到 PyPI

---

## 十、设计决策记录

所有关键决策已拍板:

| # | 议题 | 决定 |
|---|---|---|
| A | 属性系统 | **混合**:硬指标 + 软标签,关键行动才检定 |
| B | state_delta 产出 | **两次 LLM 调用**:Narrator 专注叙事,Extractor 提取 JSON。牺牲成本换体验 |
| C | 死亡机制 | **硬死亡** — HP 归零即 game over,弹出 [R] 读档 / [T] 回酒馆 / [Q] 退出 |
| D | API key | 用户自行填写,存 `~/.config/tavern/config.toml`,不做成本追踪 |
| E | 内容边界 | **完全开放**,尺度由世界作者和玩家决定 |
| F | 存档模型 | **线性存档**,不做分支;`/rewind` 只用于手滑撤销 |
| G | 玩家元能力 | 不允许手动编辑 NPC 记忆或世界状态。这是游戏,不是共创写作 |
| H | 通关 | 无硬性胜利条件,GM 判断 |
| I | 发布形态 | **开源**,鼓励社区贡献世界包 |
| J | 小说导出 | 支持 `/export novel`,保留完整 turn 日志作为素材 |
| K | 默认 LLM 后端 | **不提供**。引擎题材中立、LLM 中立,首次运行引导用户填写 |
| L | 首个内置世界 | **不预置**。所有题材由世界包提供,用户加载或创建 |
| M | 剧情推进模型 | **渐进推进**:Director 分蜜月期 / 轻推期 / 策划期三阶段介入,阈值由世界包配置 |
| N | TUI 框架 | **Textual**。组件化 + 异步 + Markdown,最接近 Claude Code 的交互形态 |

### 剩余开放问题

**无。** 所有关键决策已拍板,可以开始 M0。

---

## 十一、贡献指南(占位)

M4 阶段会完善。目前先记录方向:

- **优先鼓励世界包贡献**,而不是引擎改动。生态由世界数量决定
- 引擎改动需要覆盖测试
- 新增 LLM provider 只需实现 `tavern/llm/base.py` 的抽象接口
- 破坏性改动需要在决策记录里新增一条

---

*文档版本:v2.0 · 2026-08-11 · 拆分为三份独立文档后的首个纯开发文档*
