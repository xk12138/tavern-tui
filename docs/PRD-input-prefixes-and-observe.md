# PRD · 输入前缀语法 + 观察指令(`/who` `/where` `/inv` `/status` `/relations`)

- 状态:草案 → 已实现
- 版本:v1.0
- 日期:2026-08-11
- 依赖:v0.5.0 SQLite 存档 · v0.6.0 provider 层
- 里程碑:M1 观察指令铺位 + USAGE §五 §六 承诺兑现

---

## 一、问题陈述

USAGE.md §五向玩家承诺:

```
| 输入 | 含义 | 例子 |
| 纯文本 | 自由行动 / 混合行为 | 我走到吧台,点了一壶酒 |
| "..." | 纯台词 | "老板,来一壶最好的酒。" |
| *...* | 心理活动 / 独白 | *这人看我的眼神不对劲* |
| /xxx | 系统指令,不进入叙事 | /save |
| :xxx | 快捷动作 | :look :wait |
```

USAGE.md §六 承诺一批观察指令:

```
/who               当前场景在场的所有人物
/who <name>        某个 NPC 的已知信息
/where             当前地点描述
/inv               我的物品栏
/status            我的完整属性
/relations         与主要 NPC 的关系
```

**现状**:v0.7.0 有 `/save /load /rewind /saves /help /export /quit`(6 个)—— 观察类指令 0 个;输入前缀 0 个。**玩家最容易注意到的"承诺没兑现"**。

### 影响

| 用户 | 痛点 |
|---|---|
| **玩家** | 输入 `"你好"` 想说话,`*我不信她*` 想内心独白 —— 全被当裸文本送 GM;GM 没有意图信号,回复质量下降 |
| **玩家** | 想看现在在哪、有谁、身上什么东西 —— 全靠自己往上翻聊天记录 |
| **未来 Extractor** | 观察指令位不就绪的话,Extractor 落地后要再改 CLI 拼装展示层 —— **现在铺好指令位,Extractor 到位就自动填数据** |
| **未来 `/journal` `/wiki`** | 观察类指令的展示范式一致,先立住 |

### 为什么这轮做

- **无 LLM 依赖**:纯 REPL 编排 + 数据读展
- **完全可测**:纯函数解析 + 端到端 REPL
- **范围紧凑**:一天工作量
- **玩家立刻感知**:每一次输入都变得更"有意图"

---

## 二、目标与非目标

### 2.1 必须

1. **输入前缀解析器** `parse_input(raw: str) -> Intent`
   - 5 种意图:`say`(台词)、`think`(内心)、`action`(动作,含默认)、`slash`(系统指令,已有)、`shortcut`(快捷动作)
   - 前缀识别:`"..."` / `*...*` / `/...` / `:...`
   - 未匹配任何前缀 = `action`(默认)
2. **前缀送给 provider 的格式**:每个前缀翻译成一段结构化前缀行,便于 GM 识别
   - `say`: `Player says (aloud): "..."`
   - `think`: `Player thinks (internal): "..."`
   - `action`: `Player does: ...`
   - `shortcut`: `Player quickly does: <action>` (`:look` `:wait` 等)
3. **快捷动作字典**:`:look` `:wait` `:rest` `:inventory` `:map` `:recap` —— 一小组常用命令,展开为完整语义句
   - `:look` → `"looks around, taking in the scene"`
   - `:wait` → `"waits, watching what happens"`
   - `:rest` → `"takes a moment to rest and gather thoughts"`
   - `:inventory` → `"quickly checks their belongings"`(GM 会读到"清点物品"意图,但真正显示物品的是 `/inv` 而非 `:inventory`)
   - `:map` → `"tries to recall the layout of the area"`
   - `:recap` → `"pauses to reflect on what has happened so far"`
   - 未知 `:xxx` → 当作 `action` 处理("Player does: <xxx>"),不报错(让世界作者自行约定)
4. **5 个观察指令**
   - `/where` —— 当前场景:`world_state.current_scene`(存在时) + 世界包 `initial_tavern.name / location / description`
   - `/who [name]`:
     - 无参:列世界包 `initial_tavern.present_npcs` 里的 NPC(或"no NPCs currently in scene")
     - 有参:显示具体 NPC 的可公开信息(appearance / initial_impression / alias) —— **不显示 secrets / goals**(玩家不知道)
     - NPC 不存在 → `no such NPC 'X' in this world`
   - `/inv` —— 当前不追踪,显示 `Inventory tracking not yet implemented. Your character's items live in world memory for now.` + 世界包 template 里的 initial inventory(如果 save 有关联 template,当前**没有关联**,直接说未追踪)
   - `/status` —— 显示 save 层能拿到的:`turn_count / day / time_of_day / current_scene`(space fillers 后 Extractor 会填);再说明 HP/attributes 未追踪
   - `/relations` —— 未追踪(Extractor 之前)。友好提示:`Relationships aren't tracked yet — planned for a future release.`
5. **`/help` 更新** —— 加入输入前缀说明 + 5 个新指令
6. **完整测试**:parse_input 纯函数覆盖 + REPL e2e

### 2.2 非目标(明确不做)

- 不做 Extractor / state_delta —— 独立里程碑
- 不做 HP / 死亡分支 —— 依赖 Extractor
- 不做 `/journal` `/wiki` —— 需要 event log 数据
- 不做 `/tavern` 回酒馆软锚点 —— 需要场景切换机制
- 不做 `Ctrl+P` 命令面板 —— TUI 阶段
- 不做输入历史(`↑`/`↓`)—— 依赖 readline/TUI
- 前缀不解析 escape(比如 `\"foo`)—— 一旦遇到就当纯文本;keep it simple
- 不支持组合前缀(`*"..."*`)—— 只识别最外层第一个前缀

---

## 三、用户故事

### US-1:纯台词
> 玩家:`"老板,来一壶最好的酒。"` → GM 收到 `Player says (aloud): "老板,来一壶最好的酒。"`

**验收**:
- 单双引号被剥掉
- GM prompt 里明确"aloud"

### US-2:内心独白
> 玩家:`*这人看我的眼神不对劲*` → GM 收到 `Player thinks (internal): "这人看我的眼神不对劲"`

**验收**:
- 星号被剥掉
- GM prompt 里明确"internal thought" —— GM 不该"听到"这句话,只能理解为角色心理

### US-3:快捷动作
> 玩家:`:look` → 展开为 `Player quickly does: looks around, taking in the scene`

**验收**:
- 已知快捷动作被展开
- 未知 `:xxx` 当作普通 action 送(不 crash)

### US-4:查看当前场景
> 玩家:`/where` → 打印当前场景名 / 地点 / 描述

**验收**:
- 首屏(turn 0)`/where` 显示世界包的 initial_tavern
- 有 Extractor 追踪的 current_scene 时优先显示 current_scene 名

### US-5:查看在场 NPC
> 玩家:`/who` → 列 `initial_tavern.present_npcs`(有几个 NPC 显示几个);玩家 `/who shen-shuoshu` → 显示这个 NPC 的公开信息

**验收**:
- 未装 NPC → `(no NPCs listed for this scene)`
- 未知 NPC id → `no such NPC 'X'`
- **不泄漏 secrets / goals**

### US-6:未追踪字段友好提示
> 玩家:`/inv` `/status` `/relations` → 打印占位说明,告诉玩家这在等 Extractor

**验收**:
- 不 crash
- 语言清楚,说是"尚未实现",不做假数据

### US-7:前缀识别边界
> 玩家:`"没关掉的引号` → 当作 action;`""` 空台词 → 当作 action

**验收**:
- 前缀识别必须**匹配开头 + 匹配结尾**才算前缀语法
- 未闭合 → 当 action

---

## 四、功能规格

### 4.1 输入解析 API

```python
# src/tavern/repl/parser.py

from dataclasses import dataclass
from typing import Literal

Kind = Literal["say", "think", "action", "shortcut", "slash"]

@dataclass
class Intent:
    kind: Kind
    body: str              # cleaned text (prefixes stripped)
    raw: str               # original input, verbatim
    llm_line: str          # what gets sent to provider

def parse_input(raw: str) -> Intent: ...
```

### 4.2 解析规则

| 前缀 | 匹配 | Intent |
|---|---|---|
| `"..."` | 首字符 `"` **且** 末字符 `"`;剥掉两端引号 | say |
| `*...*` | 首字符 `*` **且** 末字符 `*`;剥掉 | think |
| `:xxx`(前缀 `:`) | 首字符 `:`;后续文本作为 shortcut key | shortcut |
| `/xxx`(前缀 `/`) | 首字符 `/`;后续作为 slash 命令 | slash |
| 其他 | | action |

**边界**:
- 输入被 `strip()` 后判定
- 空输入 → REPL 层已过滤,parser 不用担心
- 未闭合前缀(`"你好`)→ action
- 单字符 `"` 或 `*` → action(闭合规则失败)

### 4.3 送 provider 的格式

```python
def _intent_to_llm_line(intent: Intent) -> str:
    if intent.kind == "say":
        return f'Player says (aloud): "{intent.body}"'
    if intent.kind == "think":
        return f'Player thinks (internal, unheard by others): "{intent.body}"'
    if intent.kind == "shortcut":
        expanded = SHORTCUT_MAP.get(intent.body, intent.body)
        return f"Player quickly does: {expanded}"
    # default action
    return f"Player does: {intent.body}"
```

`slash` 不送 provider(在 provider 调用前被处理)。

### 4.4 快捷动作字典

```python
SHORTCUT_MAP = {
    "look": "looks around, taking in the scene",
    "wait": "waits, watching what happens",
    "rest": "takes a moment to rest and gather thoughts",
    "inventory": "quickly checks their belongings",
    "map": "tries to recall the layout of the area",
    "recap": "pauses to reflect on what has happened so far",
}
```

未知 shortcut 直接透传:`Player quickly does: <raw shortcut text>`。

### 4.5 观察指令

`/where`:

```
Current scene: 醉仙楼
Location: 洛阳城·西市
Description:
  三层木楼,雕花门窗。一楼是散座,二楼有雅间,三楼是掌柜住处。
  ...
Time: (turn 12)
```

- 优先读 `save.state.current_scene`(若非空)—— 未来 Extractor 会填
- fallback `pack.world.initial_tavern`
- `time` 字段:`save.state.time_of_day`(若非空)否则 `(turn N)`

`/who` (无参):

```
NPCs in this scene:
  - 沈先生 (shen-shuoshu) — 醉仙楼的常客,自称说书人。
```

- 数据源:`pack.world.initial_tavern.get('present_npcs', [])`
- 每个 NPC:name + id + `initial_impression.description`(前 80 char)

`/who <name-or-id>`:

```
沈先生 (shen-shuoshu)
Also known as: 说书人, 沈老
Appearance: 五十来岁,身材瘦长,右手食指有一道旧疤

Your impression:
  醉仙楼的常客,自称说书人。你听人说他讲的故事真假掺半。
```

- 支持用 id 或 name 或 alias 匹配(大小写不敏感,精确匹配)
- **不显示 secrets / goals / relations** —— 玩家不该看到
- 找不到 → `no such NPC '<x>' in this world`

`/inv`:

```
Inventory:
  (not tracked yet — Extractor coming in a future release)
```

`/status`:

```
Character status:
  turn:  12
  day:   1
  time:  (not set)
  scene: 醉仙楼

HP, attributes, and inventory aren't tracked yet — Extractor coming in a future release.
```

`/relations`:

```
Relationships:
  (not tracked yet — Extractor coming in a future release)
```

### 4.6 REPL 主循环变化

现在 `_run_play_loop` 处理输入的地方:

```python
# 现有
if line.startswith("/"):
    outcome = _handle_slash(...)
    ...
# 送 provider
reply = provider.complete(line, system=system_prompt)
```

变成:

```python
intent = parse_input(line)
if intent.kind == "slash":
    outcome = _handle_slash(intent.raw, save, pack)  # unchanged
    ...
llm_line = intent.llm_line
reply = provider.complete(llm_line, system=system_prompt)
# turn 里存"raw"作为玩家输入(便于导出小说时保真)
save.append_turn("player", intent.raw, turn_no=turn_no)
save.append_turn("gm", reply, turn_no=turn_no)
```

**关键决定**:save 里存 **raw**(玩家原本敲的),而不是 llm_line。理由:
- 导出小说时 raw 更真实(玩家真的说了"你好"而不是"Player says (aloud): 你好")
- 未来重放/回归测试可复现
- llm_line 是运行时衍生,不应该持久化

### 4.7 System prompt 更新

在 `_build_system_prompt` 里加一段说明输入约定:

```
The player uses the following input conventions:
- "..."   = the character speaks aloud
- *...*   = the character's private thoughts (do NOT let other characters hear)
- :xxx    = a quick, common action
- otherwise = a free-form action
```

**为什么这句必要?** 前缀翻译到 `Player says (aloud): "..."` 是一个信号,但让 GM 显式知道"internal 是私有的"能确保它不让 NPC 突然听到玩家的心理活动。

### 4.8 `/help` 更新

```
Input syntax:
  "..."             character speech
  *...*             internal thought
  :look :wait ...   shortcut actions
  otherwise         free-form action

System commands:
  /where            show current scene
  /who [name]       list NPCs / describe one
  /inv              show inventory (not tracked yet)
  /status           show character status
  /relations        show NPC relationships (not tracked yet)
  /save [name]      save (copy to 'name' if given)
  /load <name>      load another save
  /saves            list all saves
  /rewind [N]       undo the last N turns (default 1)
  /export novel [PATH]  rewrite this save into a prose novel
  /help             this help
  /quit, /exit      exit
```

---

## 五、实现设计

### 5.1 模块结构

```
src/tavern/
├── repl/
│   ├── __init__.py       ← re-export parse_input, Intent, SHORTCUT_MAP
│   ├── parser.py         ← Intent + parse_input + shortcut map
│   └── observe.py        ← 5 个观察指令的渲染函数
└── cli.py                (+ integration, /where /who /inv /status /relations handlers)
```

**为什么建 `repl/`**? REPL 层(输入解析、命令渲染)已经从 CLI 里分化出来 —— CLI 也就是 `_run_play_loop` + `_handle_slash` 已经接近 400 行。抽出去让 `cli.py` 只做 dispatch,`repl/` 做纯逻辑。**这一步不重构旧代码**,只把新逻辑放到新模块。

### 5.2 parser.py

```python
from dataclasses import dataclass

SHORTCUT_MAP = {...}

@dataclass
class Intent:
    kind: str
    body: str
    raw: str
    llm_line: str

def parse_input(raw: str) -> Intent:
    stripped = raw.strip()
    if not stripped:
        return _make_intent("action", "", raw)
    # slash
    if stripped.startswith("/"):
        return _make_intent("slash", stripped, raw)
    # say
    if len(stripped) >= 2 and stripped.startswith('"') and stripped.endswith('"'):
        return _make_intent("say", stripped[1:-1], raw)
    # think
    if len(stripped) >= 2 and stripped.startswith('*') and stripped.endswith('*'):
        return _make_intent("think", stripped[1:-1], raw)
    # shortcut
    if stripped.startswith(":") and len(stripped) > 1:
        return _make_intent("shortcut", stripped[1:], raw)
    # default
    return _make_intent("action", stripped, raw)

def _make_intent(kind, body, raw) -> Intent:
    return Intent(kind=kind, body=body, raw=raw, llm_line=_to_llm(kind, body))

def _to_llm(kind, body) -> str:
    if kind == "say":       return f'Player says (aloud): "{body}"'
    if kind == "think":     return f'Player thinks (internal, unheard by others): "{body}"'
    if kind == "shortcut":
        expanded = SHORTCUT_MAP.get(body, body)
        return f"Player quickly does: {expanded}"
    if kind == "slash":     return ""     # never sent
    return f"Player does: {body}"
```

### 5.3 observe.py

纯 render 函数,输入 `pack, save`,输出字符串。理由:方便单测。

```python
def render_where(pack: WorldPack, save: Save) -> str: ...
def render_who(pack: WorldPack, save: Save, arg: str = "") -> str: ...
def render_inv(pack: WorldPack, save: Save) -> str: ...
def render_status(pack: WorldPack, save: Save) -> str: ...
def render_relations(pack: WorldPack, save: Save) -> str: ...
```

### 5.4 CLI 集成

`_run_play_loop`:

```python
intent = parse_input(line)
if intent.kind == "slash":
    outcome = _handle_slash(intent.raw, save, pack)
    ...
    continue

# provider
reply = provider.complete(intent.llm_line, system=system_prompt)

# save with raw (not llm_line)
save.append_turn("player", intent.raw, turn_no=turn_no)
save.append_turn("gm", reply, turn_no=turn_no)
```

`_handle_slash` 加 5 个分支:

```python
if cmd == "/where":
    print(render_where(pack, save))
    return "continue"
# 类似 /who, /inv, /status, /relations
```

`_build_system_prompt` 追加输入约定段落。

`_print_repl_help` 更新。

### 5.5 依赖

**stdlib only**。

---

## 六、测试策略

### 6.1 单元测试

`tests/repl/test_parser.py`:
- 5 种 kind 各覆盖至少 2 用例
- 边界:空输入、未闭合前缀、单字符前缀、`:` 无内容、`""`、`**`
- llm_line 格式验证
- SHORTCUT_MAP 覆盖每个 key
- 未知 shortcut 透传

`tests/repl/test_observe.py`:
- render_where:有 current_scene / 无 current_scene fallback
- render_who:空 present_npcs / 有 NPC 列表 / 找特定 NPC / 找不到 NPC
- **不泄漏 secrets**(重要 —— 显式测试)
- render_inv / status / relations:非空、包含"not tracked"提示

### 6.2 REPL e2e

`tests/cli/test_play_prefix_and_observe.py`:
- 输入 `"你好"` 后 turn 里存 `"你好"`(raw)—— 而不是 `Player says: 你好`
- `/where` 首屏打印世界包 initial_tavern 信息
- `/who` 无参 → 显示 present_npcs
- `/who shen-shuoshu` → 打印公开信息,**不含 secrets 字符串**
- `/who nonexistent` → error 但不 crash
- `/inv` `/status` `/relations` → 打印 "not tracked yet"
- `/help` 输出包含 `Input syntax:` 段

### 6.3 覆盖率目标

- repl/parser 100%(纯函数,应能全覆盖)
- repl/observe ≥ 90%

---

## 七、风险与取舍

| 议题 | 决定 |
|---|---|
| save 里存 raw 还是 llm_line? | **raw**。玩家真敲的是"你好",不是"Player says: 你好";导出小说时 raw 更真;llm_line 是衍生 |
| system prompt 里说明输入约定? | **是**。仅靠 `Player says (aloud):` 前缀不够,显式告诉 GM"internal 是私有的" |
| 前缀支持嵌套 / 组合(`*"..."*`)? | **不**。keep it simple;未来玩家真需要再加 |
| 未知 `:shortcut` 报错还是透传? | **透传**。让世界作者可以在世界包里约定自己的 shortcut,不硬编码校验;`SHORTCUT_MAP` 是全局默认,不是唯一列表 |
| `/inv` 完全没数据要不要显示 template 里的 initial inventory? | **不**。misleading —— 玩家会以为"追踪已就绪"。宁可诚实说 "not tracked yet",不要假数据 |
| `/who <name>` 显示 goals? | **不**。玩家不该看到 —— goals 是 NPC 内心动机,应是"通过互动逐渐感受到"的 |
| `/who <name>` 显示 secrets? | **绝对不**。这是 GM 侧信息 |
| 观察指令要不要发 provider? | **不**。这些是"UI 层显示已知数据",不是"问 GM"。玩家想问 NPC 应该用 `"沈先生,你为什么摸手指?"` |
| shortcut key 大小写敏感? | **敏感**(小写)。玩家习惯 `:look` 而非 `:LOOK`;严格匹配简单 |

---

## 八、验收指标

- `parse_input` 单元测试 100% 覆盖
- 5 个观察指令都能在 REPL 里跑
- `/who <name>` **不泄漏 secrets** —— 显式测试守护
- turn 存储用 raw,不是 llm_line
- `/help` 显示输入前缀 + 全部 5 个新指令
- 总测试仍 <8 秒

---

## 九、后续联动

- **Extractor 落地时** —— save schema v2 加 NPC / faction / relations / inventory 表 → 观察指令直接读新表(展示层不变)
- **`/journal`** —— 复用 render pattern,读事件日志
- **`/wiki <topic>`** —— 复用 render pattern,读世界包 assets/glossary.md
- **`/tavern` 回酒馆** —— 复用输入前缀的 slash 分支
- **前缀 escape** —— 玩家真想说 `"literally with quotes"` 时的转义规则
