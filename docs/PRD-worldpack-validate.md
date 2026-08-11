# PRD · 世界包加载与 `tavern validate`

- 状态:草案 → 已实现
- 版本:v1.0
- 日期:2026-08-11
- 里程碑:M4 "世界包生态" 提前落地(依赖前置)

---

## 一、问题陈述

### 1.1 现状

`WORLD_BUILDING.md` 详细描述了世界包的 TOML 结构、必填字段、目录布局与最佳实践,并向用户承诺:

> 写完之后,检查前跑一下:
> ```
> tavern validate ./my-world/
> ```
> 它会检查:TOML 语法 / 必填字段 / 引用完整性 / 字段长度 / Prompt token 数

而 `DESIGN.md` 的代码结构规划里也预留了 `src/tavern/worldpack/{loader.py, schema.py}`。

**但代码库中还没有任何实现**。世界作者只能在脑子里对着文档校对,或者等到运行时看 GM 表现异常再回头 debug。

### 1.2 影响用户

| 用户 | 痛点 |
|---|---|
| **世界作者** | 无法校验作品,只能试错;失去了发布前的兜底 |
| **玩家** | 拿到别人的世界包,不知道能不能正常载入 |
| **贡献者/维护者** | 无法搭建 CI 验证社区世界包,生态难扩展 |
| **引擎自己** | M0 里程碑要求"加载 minimal-tavern 测试世界包",没有 loader 干脆跑不起来 |

### 1.3 为什么现在做

- 是**所有后续里程碑的前置**:M0 要 load 世界包,M4 要 install/search/validate
- **不依赖 LLM**,可以完整测试、真跑
- 完成后 `WORLD_BUILDING.md` 的承诺立刻兑现,世界作者立刻能用

---

## 二、目标与非目标

### 2.1 目标

**必须**:
1. 实现 `WORLD_BUILDING.md` §二 描述的完整 TOML schema
2. 提供 `tavern validate <path>` CLI 命令
3. 校验:TOML 语法、必填字段、引用完整性、字段长度合理性、简单的 token 估算
4. 支持三种入口:单文件 `world.toml` / 世界包目录 / minimal 世界(30 行就能跑)
5. 输出**分级诊断**:error(阻断) / warning(建议) / info(提示)
6. 退出码规范:0=通过,1=有 error,2=CLI 使用错误
7. 完整单元测试,fixture 覆盖 happy path 与各错误类型

**可选(本次)**:
- Python API `load_worldpack(path) -> WorldPack` 供后续里程碑使用

### 2.2 非目标(明确不做)

- 不做 `tavern install`(那是 M4 的下一步)
- 不做 `tavern search`(社区索引需要中心仓库)
- 不做 UI 交互(纯 CLI + 文本输出)
- 不接 LLM(校验器纯静态)
- 不做 schema 迁移工具(v1 之前不承诺兼容)

---

## 三、用户故事

### US-1:第一次写完 world.toml,想快速验证
> "作为世界作者,我写了 30 行 minimal world.toml,我希望 `tavern validate ./my-world.toml` 3 秒内告诉我能不能用。"

**验收**:
- 单文件 world.toml,退出码 0,输出 `OK · 1 world validated` 之类
- 有 TOML 语法错误 → 退出码 1,精确报出行号

### US-2:写完带 NPC 目录的完整世界包
> "作为世界作者,我的 `my-world/` 里有 `npcs/shen.toml`,`world.toml` 里 `present_npcs = ["shen"]`。我想确认所有引用是对的。"

**验收**:
- 引用存在的 NPC id → 通过
- 引用了 `npcs/` 里没有的 id → error,指明缺哪个
- NPC 卡不必要字段(如 `card.appearance` 缺失)只给 warning,不阻断

### US-3:字段写得太长
> "我不小心把 `world.setting.tone` 写了 3000 字。我希望校验器提醒我,GM prompt 会太长。"

**验收**:
- 单字段超过配置阈值 → warning
- 整个世界估算 token > 阈值 → warning + 分项统计

### US-4:CI 校验社区世界包
> "作为维护者,我在 GitHub Actions 里跑 `tavern validate examples/*/`,只要有一个包坏,就让 CI 挂掉。"

**验收**:
- 支持传目录,自动发现 `world.toml`
- 通过退出码区分 pass/fail
- 支持 `--json` 输出机读结果(**本次先做人读格式,`--json` 留作 P1**)

---

## 四、功能规格

### 4.1 CLI 接口

```
tavern validate <PATH> [--strict] [--verbose]

参数:
  PATH        单文件 world.toml,或包含 world.toml 的目录

选项:
  --strict    warning 也视为失败(用于严格 CI)
  --verbose   打印所有 info / 校验过程

退出码:
  0    通过(可能有 warning,非 strict 下不算失败)
  1    存在 error 或 (strict 下)warning
  2    CLI 使用错误(路径不存在等)
```

### 4.2 校验规则清单

按严重程度分级:

#### E · Error(必错,阻断)

| ID | 规则 |
|---|---|
| E001 | 路径不存在,或既不是文件也不是目录 |
| E002 | `world.toml` 不存在(目录模式) |
| E003 | TOML 语法错误(报行号) |
| E004 | 缺必填字段:`world.id` / `world.name` / `world.setting` / `world.initial_tavern` |
| E005 | `world.id` 不是合法 slug(`^[a-z0-9][a-z0-9_-]*$`) |
| E006 | `world.version` 不是合法 SemVer |
| E007 | `initial_tavern.present_npcs` 里的 id 在 `npcs/` 下不存在 |
| E008 | `npcs/*.toml` 里 `npc.id` 与文件名不一致 |
| E009 | NPC id 重复(两个文件同 id) |
| E010 | 模板文件里 `pc.hp.current > pc.hp.max` |
| E011 | 引用了不存在的模板/势力/地点 |

#### W · Warning(建议,非 strict 不阻断)

| ID | 规则 |
|---|---|
| W001 | `world.description` / `intro.md` 缺失(玩家会没背景交代) |
| W002 | 没有任何 `[[world.factions]]`(冲突扁平) |
| W003 | 没有任何 `[[world.timeline]]`(世界缺乏历史厚度) |
| W004 | 单字段字符数 > 2000(建议拆分) |
| W005 | 世界包总估算 token > 8000(会烧 prompt 预算) |
| W006 | 没有任何 template(新手 3 分钟建角色路径缺失) |
| W007 | `plot_pacing.honeymoon_turns > 200`(玩家可能永远看不到主线) |
| W008 | `initial_tavern.opening_hook` 缺失或过短(<50 字符,开局体验差) |
| W009 | 某 NPC 卡缺 `goals` 或 `secrets`(GM 难以演活) |

#### I · Info(提示,verbose 才显示)

| ID | 规则 |
|---|---|
| I001 | 统计:X NPC,Y faction,Z template,估算 ~N tokens |
| I002 | 使用的可选字段列表 |

### 4.3 Token 估算算法

**简单启发式**(不引入 tiktoken 等外部依赖):

```
tokens ≈ ceil(chinese_chars * 0.6 + non_chinese_chars * 0.25)
```

对英文平均 4 char/token、中文平均 1.7 char/token 的常见 tokenizer 表现,量级近似即可。校验时只用于 warning,不做精确计费。

### 4.4 数据模型(Python)

```python
@dataclass
class WorldPack:
    world: World                      # world.toml 的 [world] 段
    npcs: dict[str, NPC]              # id -> NPC (from npcs/)
    locations: dict[str, Location]    # 同上
    templates: dict[str, Template]    # 同上
    intro: str | None                 # intro.md 内容
    path: Path                        # 原始路径
    estimated_tokens: int

@dataclass
class Diagnostic:
    level: Literal["error", "warning", "info"]
    code: str            # E001 / W004 / I001
    message: str
    location: str | None # "world.toml:12" 或 "npcs/shen.toml"
    hint: str | None     # 修复建议

@dataclass
class ValidationReport:
    ok: bool             # 无 error 即 True(与 strict 无关)
    diagnostics: list[Diagnostic]
    pack: WorldPack | None
```

### 4.5 输出格式(人读)

```
$ tavern validate ./my-world/

world.toml
  ✗ E004  world.setting is required
          → add [world.setting] section with at minimum `era` and `tone`
  ⚠ W002  no factions defined
          → world may feel flat; consider adding [[world.factions]]

npcs/shen.toml
  ⚠ W009  npc.card.secrets is empty
          → NPCs without secrets are harder for the GM to play convincingly

── Summary ──
1 error · 2 warnings · 3 npcs · ~4823 tokens
Validation failed.
```

- 使用 ANSI 色(可通过 `NO_COLOR` env 关掉)
- Error 用 ✗ 红,Warning 用 ⚠ 黄,Info 用 ℹ 蓝
- 每条诊断给出**位置** + **可选修复建议**

---

## 五、实现设计

### 5.1 模块结构

```
src/tavern/
├── __init__.py
├── cli.py                    # entry point (tavern命令)
└── worldpack/
    ├── __init__.py
    ├── schema.py             # dataclass 模型 + 常量
    ├── loader.py             # 从磁盘装载 → WorldPack
    ├── validator.py          # 规则引擎 → ValidationReport
    ├── diagnostics.py        # Diagnostic + 格式化输出
    └── tokens.py             # 简易 token 估算
```

### 5.2 依赖

- Python 3.11+
- **stdlib only** 用 `tomllib` 解析(3.11 内置),避免额外依赖
- 无第三方运行时依赖 —— 校验器要能在最小环境跑

### 5.3 关键流程

```
tavern validate <path>
     ↓
loader.load(path):
   - 检 E001/E002
   - 解析 world.toml (捕 E003)
   - 递归解析 npcs/ locations/ templates/
   - 组装 WorldPack
     ↓
validator.validate(pack):
   - 顺序跑所有规则,每条产 0..N Diagnostic
   - 累加得 ValidationReport
     ↓
diagnostics.render(report):
   - 分组打印 → stdout
   - 计算退出码
```

### 5.4 边界与异常

- 目录里有 `world.toml` 语法错 → 打印 E003 并**停在这**,后续文件不再深入(因为主 schema 都未知,信息价值低)
- 单个 NPC 文件语法错 → 单独 E003,不影响其他 NPC 校验
- I/O 错误(权限不足)→ 退出码 2,不作为 validation 失败

---

## 六、测试策略

### 6.1 单元测试(pytest)

- `tests/worldpack/test_loader.py` —— 装载覆盖率
- `tests/worldpack/test_validator.py` —— 每条 rule 一个正+负用例
- `tests/worldpack/test_tokens.py` —— 中英文 token 估算稳定性
- `tests/cli/test_validate_command.py` —— 端到端跑 `python -m tavern validate ...`

### 6.2 Fixture

`tests/fixtures/` 提供:

- `minimal-ok/world.toml` —— WORLD_BUILDING.md §十 示例
- `full-ok/` —— 有 npcs/locations/templates/ 齐全的世界
- `broken-toml/world.toml` —— 语法错
- `missing-required/world.toml` —— 缺 `world.setting`
- `bad-ref/` —— `present_npcs` 引用不存在的 npc
- `over-token/world.toml` —— 触发 W005
- `no-factions/world.toml` —— 触发 W002

### 6.3 验收清单

- [x] 全部规则至少一个正样本 + 一个负样本
- [x] 覆盖率 ≥ 85%(worldpack/ 目录)
- [x] CLI happy path 5 秒内返回
- [x] 退出码正确(0/1/2)
- [x] `NO_COLOR=1` 时输出不含 ANSI

---

## 七、风险与取舍

| 议题 | 取舍 |
|---|---|
| **要不要引入 pydantic?** | 不。stdlib dataclass + 手写校验足够,减少依赖利于分发 |
| **token 估算精度?** | 只用于 warning,不精确;后续接 tokenizer 也不算破坏性 |
| **schema 版本化?** | v1 之前不保证兼容;`world.version` 是**世界包内容**的版本,不是 schema 版本。schema 版本用 loader 内部常量控制 |
| **要不要支持 YAML?** | 不。TOML 是设计决策 K/L,保持一致 |
| **国际化?** | 首版 diagnostic 消息只做英文(方便社区贡献),后续可增 i18n |

---

## 八、后续里程碑联动

本 PRD 交付后,以下里程碑可以直接依赖:

- **M0**:orchestrator 用 `load_worldpack(path)` 装 minimal-tavern
- **M4**:`tavern install` 复用 loader + validator,拒绝装校验不过的包
- **CI**:所有 examples/ 下的世界包每次 push 都跑 `tavern validate --strict`

---

## 九、验收指标

发布后追踪:

1. `tavern validate examples/minimal-tavern/` 通过
2. 每条错误规则至少 1 个 test 覆盖
3. 世界作者从"改完 → 知道对不对"耗时 ≤ 5 秒
4. `tavern --help` 显示 `validate` 子命令

---

*本 PRD 已随实现同步交付,若后续有变更以最新 commit 为准。*
