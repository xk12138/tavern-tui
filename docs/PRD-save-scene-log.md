# PRD · 场景日志 + SQLite 存档 + `/save` `/load` 系统指令

- 状态:草案 → 已实现
- 版本:v1.0
- 日期:2026-08-11
- 依赖:v0.4.0 的 `tavern play` REPL
- 里程碑:M1 第一块拼图

---

## 一、问题陈述

v0.4.0 之后 `tavern play` 能跑了,但**每次退出即忘**。玩家第一次玩、玩到第 30 回合、发现晚饭要冷了 —— 按 Ctrl+C 之后**全没了**。

USAGE.md §六第一段承诺的所有指令都还是空的:

```
/save [name]       存档。省略 name 则覆盖当前存档
/load [name]       载入
/saves             列出所有存档
/rewind            回退上一回合(手滑撤销;死亡后不可用)
```

DESIGN.md §九 M1 明文要求:

> 结构化 `world_state` + `scene_log`,持久化到 SQLite

DESIGN.md §六 数据模型草图里的 `scene_log` 表也定下来了。**现在是把它落地的时机**。

### 影响

| 用户 | 痛点 |
|---|---|
| **玩家** | 玩一次就废;没法"下班存档明天继续";一切进展归零 |
| **未来的 Extractor** | `state_delta` 需要写到某个 `world_state` 表里 —— 表不存在 |
| **未来的 `/export novel`** | 依赖完整 `scene_log`(原文,不压缩)—— DESIGN.md §四关键节点写死了 |
| **未来的 Memory Keeper** | 场景摘要需要 turn 日志作为输入源 |

### 为什么这轮做

- **可完整测试**:纯 stdlib `sqlite3`,零网络,零 LLM
- **玩家立刻有价值**:save/load 是"能玩"和"能真正玩"的分水岭
- **地基**:scene_log 一落地,后续 Extractor / novel export / rewind 全部有存放点

---

## 二、目标与非目标

### 2.1 必须

1. **SQLite 存档层**:一个存档 = 一个 `.db` 文件,放在 `<tavern_home>/saves/<name>.db`
2. **表结构**:`scene_log`(turns) + `world_state`(单行) + `save_meta`(schema 版本等)
3. **API**:
   - `Save.new(world_id, save_name)` —— 建新存档
   - `Save.open(save_name)` —— 打开已有存档
   - `save.append_turn(role, text)` —— 写一 turn
   - `save.turns()` —— 读所有 turn(按顺序)
   - `save.state` —— 读/写 world_state(turn_count/current_scene/day/time)
   - `save.rewind(n=1)` —— 删掉最后 n 对 turn(玩家+GM)
   - `save.close()` —— 关连接
4. **`tavern play` 集成**:
   - 启动时:若 `--save <name>` 传了 → 打开;否则**自动新建**一个 `default-<world_id>` 存档
   - 每回合玩家输入 + GM 回复 → 双 turn 写入
   - `turn_count += 1` per 回合(1 回合 = 1 对 turn)
5. **新系统指令**(在 `tavern play` REPL 内):
   - `/save [name]` —— 存到指定名字(略名字则原地保存,tavern 自动 flush 所以其实是"确认已存")
   - `/load <name>` —— 载入 → 打印摘要 + 恢复
   - `/saves` —— 列表
   - `/rewind` —— 回退最近一回合
   - `/help` —— 打印指令表
   - `/quit` 之外的其他指令保持 `[unknown command]` 反馈,不吃到 provider
6. **`tavern saves` 顶层子命令**:与 REPL 内 `/saves` 内容一致,方便外部脚本
7. **schema 迁移策略**:`save_meta.schema_version` 存版本号,不匹配就拒绝加载(打印升级说明)。**首版 schema = 1**

### 2.2 非目标(明确不做)

- 不做 Extractor / state_delta —— 下一轮
- 不做 HP / 死亡分支 —— 依赖 state_delta
- 不做 NPC / faction / timeline 独立表 —— 依赖 state_delta
- 不做向量记忆 / 场景摘要(Memory Keeper) —— 归入 M3
- 不做 `/export novel` —— M3
- 不做 auto-save 每 N 回合 —— 每回合都 flush,不需要
- 不做多分支存档(git-style)—— DESIGN.md 决策 F "线性存档"
- 不加密存档

---

## 三、用户故事

### US-1:开局就有存档
> "作为玩家,我 `tavern play example-jianghu`,不用做什么,就应该在自动存档里。退出后再进,故事从上次的位置继续。"

**验收**:
- 首次进 → 自动建 `default-example-jianghu.db`,写入 opening_hook 作为第一条 GM turn
- 输入几行、退出、再进 → 看到之前的 GM 回复,继续玩
- turn_count 正确累加

### US-2:命名存档
> "作为玩家,玩到关键节点,我 `/save my-first-run`,以后可以 `/load my-first-run` 回来。"

**验收**:
- `/save my-first-run` → 拷贝当前存档到 `my-first-run.db`
- `/saves` 列表里出现
- `/load my-first-run` 从任何时候都能回

### US-3:手滑撤回
> "作为玩家,我不小心输了 '我拔剑砍向国王',按了回车,GM 已经开始 roll。/rewind 应该把这次和 GM 的回复都撤掉。"

**验收**:
- 从数据库删掉最后 2 条 turn(一对)
- turn_count 减 1
- 打印 "Rewound 1 turn."

### US-4:CI/脚本查看存档
> "作为脚本,我想不进 REPL 也能看已有存档。`tavern saves` 应该列表。"

**验收**:
- 打印 name / world / turn_count / mtime,人读表格
- `tavern saves --long` 打印 path

### US-5:Schema 变更不炸
> "作为未来的用户,升级到新版 tavern 后老存档如果 schema 变了,应该有清楚提示,不是 sqlite error。"

**验收**:
- 打开 `save_meta.schema_version != SCHEMA_VERSION` 的存档 → 报错:"save was created by tavern schema vX, current is vY. See docs/..."

---

## 四、功能规格

### 4.1 目录布局

```
<tavern_home>/
├── config.toml
├── worlds/
│   └── <world-id>/
└── saves/                          ← 新
    ├── default-example-jianghu.db
    ├── my-first-run.db
    └── slot-2.db
```

### 4.2 存档命名

- **合法字符**:`^[a-zA-Z0-9][a-zA-Z0-9_.-]*$`,`≤64` 字符
- 不允许 `/` `\` `.` 开头
- CLI 层校验,底层不管路径拼装(避免 path traversal)

### 4.3 SQLite Schema(version 1)

```sql
-- Schema + world binding metadata (single row)
CREATE TABLE save_meta (
    id                INTEGER PRIMARY KEY CHECK (id = 1),
    schema_version    INTEGER NOT NULL,
    world_id          TEXT NOT NULL,
    save_name         TEXT NOT NULL,
    created_at        TEXT NOT NULL,           -- ISO 8601 UTC
    tavern_version    TEXT NOT NULL
);

-- Mutable world state (single row)
CREATE TABLE world_state (
    id                INTEGER PRIMARY KEY CHECK (id = 1),
    turn_count        INTEGER NOT NULL DEFAULT 0,
    current_scene     TEXT NOT NULL DEFAULT '',
    day               INTEGER NOT NULL DEFAULT 1,
    time_of_day       TEXT NOT NULL DEFAULT '',
    updated_at        TEXT NOT NULL
);

-- Append-only turn log
CREATE TABLE scene_log (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    turn_no           INTEGER NOT NULL,        -- pair index (1..)
    role              TEXT NOT NULL CHECK (role IN ('player','gm','system')),
    text              TEXT NOT NULL,
    created_at        TEXT NOT NULL
);
CREATE INDEX idx_scene_log_turn ON scene_log(turn_no);
```

**为什么每 turn 是一条,而不是"一回合一条"?** DESIGN.md §六 明确写 `turns: [{role, text, timestamp}]` —— 保留原始日志,供小说导出。分开存 player 和 gm 两条更接近事实,`turn_count` 通过 `turn_no` 表达"逻辑回合"。

### 4.4 Python API

```python
# src/tavern/save/store.py

@dataclass
class SaveState:
    turn_count: int
    current_scene: str
    day: int
    time_of_day: str

@dataclass
class Turn:
    id: int
    turn_no: int
    role: str            # "player" | "gm" | "system"
    text: str
    created_at: str

class Save:
    def __init__(self, path: Path): ...

    @classmethod
    def new(cls, name: str, world_id: str) -> "Save": ...
    @classmethod
    def open(cls, name: str) -> "Save": ...

    @property
    def path(self) -> Path: ...
    @property
    def world_id(self) -> str: ...
    @property
    def name(self) -> str: ...
    @property
    def state(self) -> SaveState: ...

    def append_turn(self, role: str, text: str) -> Turn: ...
    def turns(self, limit: int | None = None) -> list[Turn]: ...
    def rewind(self, pairs: int = 1) -> int: ...   # returns turns deleted

    def update_state(self, **fields) -> None: ...
    def copy_to(self, new_name: str) -> "Save": ...
    def close(self) -> None: ...

# module-level helpers
def list_saves() -> list[SaveSummary]: ...
def delete_save(name: str) -> None: ...
def save_path(name: str) -> Path: ...

class SaveError(Exception): ...          # base
class SaveNameError(SaveError): ...      # illegal chars / too long
class SaveNotFoundError(SaveError): ...
class SaveExistsError(SaveError): ...
class SchemaMismatchError(SaveError): ...
```

**API 契约**:
- `Save.new(name)` —— name 已存在则抛 `SaveExistsError`(除非调用方先 `delete_save`)
- `Save.open(name)` —— 不存在抛 `SaveNotFoundError`
- 所有 write 立即 commit(SQLite autocommit off,`with save._conn:` context 包)
- `close()` 是幂等的
- 打开时立刻校验 `schema_version`,不匹配抛 `SchemaMismatchError`

### 4.5 `tavern play` 集成

```
tavern play <WORLD_ID> [--provider ROLE] [--save NAME] [--new]

  --save NAME    open (or create) the named save
  --new          force a fresh save (deletes existing default-<world_id>)
```

默认存档策略:
- `--save NAME` 传了 → 存在就 open,不存在就 new
- 没传 → 用 `default-<world_id>`。存在 open,不存在 new
- `--new` → 先 delete default-<world_id>,再 new

首屏输出增加一行:
```
── 江湖夜雨 · 醉仙楼 ──          (save: default-example-jianghu · 12 turns)

(existing opening_hook + provider info)
```

已有 turn > 0 时,重进不再打印 opening_hook —— 而是打印最近 3 turn 摘要:

```
── continuing from turn 12 ──
[player] 走到角落去看看那个说书人
[gm] 你走近他,他的手不自觉摸了下食指
[player] 坐下来问他今天讲什么故事
...
```

### 4.6 REPL 指令(在 play 循环内)

| 指令 | 行为 |
|---|---|
| `/save [name]` | 无 name:确认已存(打印 `Saved. (turn N)`);有 name:copy 到新名字并切换到新存档 |
| `/load <name>` | 关当前,打开 name。找不到 → error 但不退 REPL |
| `/saves` | 表格:name / world / turn_count / mtime |
| `/rewind [n]` | 撤销 n 个回合(默认 1)。n≤0 或超总数 → error 提示 |
| `/help` | 打印所有指令 |
| `/quit` `/exit` | 退出 |
| 其他 `/xxx` | `[unknown command] type /help` |

**空指令行**(比如仅回车):跳过,不进 provider

### 4.7 `tavern saves` 顶层命令

```
tavern saves [--long]

输出:
NAME                        WORLD              TURNS  UPDATED
default-example-jianghu     example-jianghu    12     2026-08-11 15:47
my-first-run                example-jianghu    30     2026-08-11 16:12

--long 加 path 列。空列表打印 "No saves yet."
```

### 4.8 输入行的边界

- `\n` `\r` 剥掉
- 存 turn 时用 `text = raw`,不做二次编码
- 允许中英文、emoji;SQLite `TEXT` 存 UTF-8

### 4.9 错误路径

| 情况 | 行为 |
|---|---|
| 存档名非法 | `SaveNameError`;CLI 层退出 1,提示合法字符集 |
| 加载不存在的存档 | `SaveNotFoundError`;REPL 内不 crash,只 error msg |
| Schema 不匹配 | `SchemaMismatchError`;CLI 层退出 1 提示 upgrade path |
| SQLite disk error | 让原生 `sqlite3.Error` 上抛;顶层 CLI 打印后退出 2 |

---

## 五、实现设计

### 5.1 模块结构

```
src/tavern/save/
├── __init__.py       ← re-export public API
├── schema.py         ← SCHEMA_VERSION + CREATE TABLE strings
└── store.py          ← Save class + list_saves / delete_save
```

### 5.2 依赖

**stdlib only**:`sqlite3`,`pathlib`,`dataclasses`,`datetime`。

### 5.3 关键实现要点

**Save.__init__** 直接接 Path;`new` / `open` 是工厂。

**Connect 参数**:
- `sqlite3.connect(path, isolation_level=None)` —— 手动管事务,配合 `BEGIN` / `COMMIT`
- `PRAGMA foreign_keys = ON`(哪怕我们不用外键,养成习惯)
- `PRAGMA journal_mode = WAL`(并发读没意义,单文件写入,更好性能)

**Schema 创建**:一次性 `executescript`,`IF NOT EXISTS` 保护。

**append_turn**:
```python
with self._conn:
    self._conn.execute("BEGIN")
    self._conn.execute(
        "INSERT INTO scene_log (turn_no, role, text, created_at) VALUES (?,?,?,?)",
        (turn_no, role, text, now_iso()),
    )
```

turn_no 计算:
- 玩家新 turn = 目前最大 turn_no + 1
- GM 紧跟 = 同一个 turn_no
- 或者:每 append_turn 显式接受 `turn_no` —— **PRD 选后者,更清晰**

REPL 层调用:
```python
turn_no = save.state.turn_count + 1
save.append_turn("player", line, turn_no=turn_no)
save.append_turn("gm", reply, turn_no=turn_no)
save.update_state(turn_count=turn_no)
```

**rewind(pairs)**:
```sql
DELETE FROM scene_log WHERE turn_no > (SELECT MAX(turn_no) - ? FROM scene_log)
```
然后 `turn_count = max(turn_no) OR 0`。

### 5.4 迁移(future-proofing)

`save_meta.schema_version` 存 int。**首版 = 1**。

未来 v2 加字段时:
- `SCHEMA_VERSION = 2`
- Add `MIGRATIONS[(1,2)] = list_of_sql`
- `Save.open` 检测到 old version → 自动 apply(留在下一次 PRD)

**本轮不实现迁移执行代码**,只留检测。跨版本先要求"备份 → 用新版重新玩"。

### 5.5 时间戳

- 所有 `created_at` / `updated_at` = `datetime.now(tz=UTC).replace(microsecond=0).isoformat()` + "Z"

### 5.6 存档名 → path

```python
_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$")

def save_path(name: str) -> Path:
    if not _NAME_RE.match(name):
        raise SaveNameError(name)
    return saves_dir() / f"{name}.db"

def saves_dir() -> Path:
    return tavern_home() / "saves"
```

### 5.7 REPL 集成

`_cmd_play` 变化:

```python
save = _open_or_new_save(world.id, args.save, args.new)

# print header + resume-or-open
if save.state.turn_count == 0:
    print_opening_hook(pack)
    save.append_turn("system", str(pack.world.initial_tavern.get("opening_hook","")))
else:
    print_resume_summary(save)

while True:
    line = read_line()
    if not line: continue
    if line.startswith("/"):
        if handle_slash(line, save, pack): continue  # returns True to continue loop
        else: break   # /quit
        continue
    reply = provider.complete(line, system=...)
    turn_no = save.state.turn_count + 1
    save.append_turn("player", line, turn_no=turn_no)
    save.append_turn("gm", reply, turn_no=turn_no)
    save.update_state(turn_count=turn_no)
    print(reply)
```

---

## 六、测试策略

### 6.1 单元测试(pytest)

- `tests/save/test_store.py`
  - Save.new / open / not_found / already_exists
  - append_turn / turns / rewind
  - update_state 各字段
  - copy_to
  - close idempotent
  - Schema mismatch detection(手动改 save_meta.schema_version 后重开)
- `tests/save/test_names.py`
  - `_NAME_RE` 边界:字母开头、含 `.`、`_`、`-`、64 字符边界、非法字符
- `tests/save/test_paths.py`
  - `save_path()` 用 tavern_home fixture 隔离

### 6.2 REPL / CLI 端到端

- `tests/cli/test_play_save_integration.py`
  - Play + 输入 3 行 + /quit → 再 open 看 turns 数 = 3 对
  - `/save my-run` 复制后 `/saves` 里有
  - `/rewind` 后 turns 数减 1 对
  - `/load nonexistent` 不 crash,继续 REPL
- `tests/cli/test_saves_command.py`
  - 空态 / 单条 / 多条 / --long

### 6.3 覆盖率目标

- `save/` 模块 ≥ 90%
- 总覆盖率不下降

### 6.4 隔离

复用 `tavern_home` fixture,所有测试用 tmp_path。

---

## 七、风险与取舍

| 议题 | 决定 |
|---|---|
| 每 turn 一条 vs 一回合一条(合并 player+gm)? | **每 turn 一条**。DESIGN.md §六如此;拆分让 role 显式,rewind/export 逻辑清晰 |
| 事务粒度? | **每次 write 一个事务**。SQLite 单文件本就快,不需要批量 |
| 用 JSON 存 turn 还是 SQL 列? | **列**。查询友好,rewind/count 直接 SQL |
| 存原始 prompt 还是玩家输入? | **玩家输入**。原始 system prompt 是 provider 拼装的,不属于历史 |
| WAL vs DELETE journal? | **WAL**。奔溃安全性好,多一个 `-wal` `-shm` 文件是可接受的 |
| 存档间共享 `world.toml`? | **是**。存档只存 world_id;每次 load 时从 worldpack 目录读 world.toml |
| 用户删了世界包后老存档还能开? | **可以打开(读 turns/state)但无法继续玩**。play 命令启动时会检查 world 是否装,不装就 error |
| `/rewind` 死亡后不可用? | **本 PRD 无死亡机制**,不适用;规则保留到后续 PRD |
| copy_to 时 SQLite 是否需要 backup API? | **是**。用 `Connection.backup()`,原生原子拷贝 |

---

## 八、验收指标

- `tavern play example-jianghu` → 输入 3 行 → Ctrl+D → 重进 → 看到之前 3 对 turn
- `/save named-run` → `/saves` 里出现 named-run
- `/rewind` → 最后一对 turn 消失
- `tavern saves` 顶层命令输出与 `/saves` 一致
- 覆盖率 save/ ≥ 90%
- 总测试仍 < 5 秒跑完

---

## 九、后续联动

- **下一轮 Extractor** —— 复用 `save.update_state()` 写 state_delta 里的字段
- **`/export novel`** —— 读 `save.turns()`,重新组稿成小说
- **`/who` `/where` `/inv`** —— 依赖 state_delta,先有 Extractor
- **Memory Keeper** —— 读 `save.turns()` 做场景摘要,写到独立 `scene_summary` 表(schema v2)
- **死亡分支** —— HP=0 时 lock save(不允许 append_turn 除非重开)
