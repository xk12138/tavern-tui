# PRD · LLM 配置管理(`tavern config`)

- 状态:草案 → 已实现
- 版本:v1.0
- 日期:2026-08-11
- 依赖:v0.2.0 交付的 `~/.config/tavern/` 目录布局

---

## 一、问题陈述

USAGE.md §三 承诺:

> 首次启动会引导你填 API key,写入到 `~/.config/tavern/config.toml`。你也可以随时手动编辑这个文件。

USAGE.md §十一疑难解答:

> 检查 `~/.config/tavern/config.toml` 语法是否正确(用 `tavern config check`)

**现状**:`tavern config` 完全不存在。用户拿到 `tavern install` 装好了世界包,但**下一步无路可走** —— 想配 LLM 只能手动写 TOML,写错了没人告诉他哪错了。

### 影响

| 用户 | 痛点 |
|---|---|
| **玩家** | USAGE.md 的"3 分钟上手"承诺断了链——`tavern install` 之后,`tavern` 一敲就是个"没配 LLM"的死胡同 |
| **未来的 LLM Provider 层(P2 下一步)** | 需要一个统一的地方读密钥,现在缺 |
| **文档承诺** | `tavern config check` 明文写在疑难解答里 |

### 为什么是 P2.1 的关键

- **M0 里程碑的最后一块拼图** —— DESIGN.md §九 M0 要求"首次运行引导:填 API key"
- **LLM Provider 抽象的硬前置** —— 没有 config 就没有 key,没有 key 就跑不通 Narrator
- **仍无 LLM 依赖** —— 纯 TOML 读写,可完整测试

---

## 二、目标与非目标

### 2.1 必须

1. `tavern config init` —— 交互式向导(第一次或 `--force` 覆盖)
2. `tavern config show` —— 打印当前配置(**遮蔽密钥**)
3. `tavern config check` —— 校验语法和字段合法性
4. `tavern config path` —— 打印配置文件绝对路径(方便 `$(tavern config path)` 用法)
5. 支持 `USAGE.md §3.2` 描述的完整 config 结构:`[llm.default]` `[llm.extractor]` `[llm.director]` `[ui]` 等
6. `TAVERN_CONFIG_HOME` 覆盖 —— 复用 v0.2.0 的 `tavern.config` 模块
7. 环境变量 fallback —— `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` 等,配置里 key 留空时自动读环境

### 2.2 非目标

- 不实际调用 LLM 验证 key 有效性(网络依赖,单独一个 `tavern doctor` 未来的事)
- 不管理多套 profile(切换 provider 直接改文件即可)
- 不做 `tavern config set <key> <value>` 编辑器接口(用户直接编辑 TOML 更直接)
- 不加密密钥(存明文 TOML 是 CLI 工具惯例;想加密可用系统 keychain,归入 P4+)

---

## 三、用户故事

### US-1:第一次用,不知道该配啥
> "作为新用户,`tavern config init` 应该问我 provider、model、api_key 三件事,然后写盘。"

**验收**:
- 支持 `anthropic / openai / deepseek / ollama / custom`
- 提供每个 provider 的合理默认 model
- 不能用 `--yes` 无人值守(密钥是必须的,不敢自动填空)
- 已存在 `config.toml` 时默认拒绝,`--force` 覆盖

### US-2:忘了自己配的啥
> "`tavern config show` 应该打印当前配置,但**不能显示完整 API key**——遮蔽成 `sk-a...c3f2`。"

**验收**:
- 密钥字段(`api_key` / `token` / 任何含 `key` 或 `secret` 的键)自动遮蔽
- 展示格式:前 4 后 4,中间 `...`;长度不足 8 直接显示 `***`

### US-3:改完文件想验证
> "手动编辑之后,`tavern config check` 应该告诉我 TOML 是否合法、字段是否齐全、api_key 是否非空。"

**验收**:
- TOML 语法错 → 报行号 + 退出 1
- `[llm.default]` 缺失 → 报错并给出补齐提示
- `provider` 不在合法枚举里 → 报错
- `api_key` 空且对应环境变量也不存在 → warning(不是 error,允许用 Ollama 无 key 场景)
- 全绿输出 `Config OK. provider=<x>, model=<y>`

### US-4:脚本调用配置路径
> "我想在 shell 里 `cat $(tavern config path)`。"

**验收**:
- 输出单行绝对路径,无其他内容
- 即使文件不存在也返回预计路径(供脚本创建用)

### US-5:环境变量兜底
> "作为 CI 用户,我不想把 key 存文件里。`ANTHROPIC_API_KEY=xxx tavern ...` 应该能跑。"

**验收**:
- config.toml 里 `api_key = ""` 且 `provider = "anthropic"` 时,读环境的 `ANTHROPIC_API_KEY`
- `tavern config check` 会指出"key 来自环境变量"

---

## 四、功能规格

### 4.1 CLI 接口

```
tavern config init [--force] [--provider PROVIDER]

  --force            覆盖已有 config.toml
  --provider PROV    非交互:指定 provider 后仍需交互填 api_key 与 model

tavern config show [--reveal]

  --reveal           展示完整密钥(需要显式打开,防止误 paste 到公开场合)

tavern config check

tavern config path
```

**退出码**:
- 0 成功
- 1 校验失败 / init 拒绝覆盖 / 找不到 config
- 2 CLI 使用错误

### 4.2 config.toml 结构(与 USAGE.md §3.2 完全一致)

```toml
[llm.default]
provider = "anthropic"
model    = "claude-sonnet-5"
api_key  = "sk-ant-..."          # 或留空,由环境变量兜底

# 可选:让 Extractor 用便宜模型
[llm.extractor]
provider = "deepseek"
model    = "deepseek-chat"
api_key  = "sk-..."

# 可选:让 Director 用强模型
# [llm.director]
# provider = "anthropic"
# model    = "claude-opus-5"

# 可选:本地 Ollama
# [llm.default]
# provider = "ollama"
# model    = "qwen2.5:14b"
# base_url = "http://localhost:11434"

[ui]
typewriter_speed_ms = 20
color_scheme        = "default"
```

**关键字段**:
- **必填(在 `[llm.default]` 里)**:`provider`
- **一般必填**:`model`(除非用了不需要模型选的 provider,未来预留)
- **必填但可来自环境**:`api_key`(Ollama 例外)
- **可选**:`base_url`(custom / ollama 才用)

### 4.3 Provider 元信息

```python
PROVIDERS = {
    "anthropic": {
        "default_model": "claude-sonnet-5",
        "env_key": "ANTHROPIC_API_KEY",
        "needs_key": True,
    },
    "openai": {
        "default_model": "gpt-4o",
        "env_key": "OPENAI_API_KEY",
        "needs_key": True,
    },
    "deepseek": {
        "default_model": "deepseek-chat",
        "env_key": "DEEPSEEK_API_KEY",
        "needs_key": True,
    },
    "ollama": {
        "default_model": "qwen2.5:14b",
        "env_key": None,
        "needs_key": False,
        "default_base_url": "http://localhost:11434",
    },
    "custom": {
        "default_model": "",
        "env_key": None,
        "needs_key": True,
    },
}
```

### 4.4 密钥遮蔽算法

```python
def mask_secret(v: str) -> str:
    if len(v) < 8:
        return "***" if v else ""
    return f"{v[:4]}...{v[-4:]}"
```

**遮蔽字段规则**:
- 字段名(大小写不敏感)包含 `key` / `secret` / `token` / `password` / `apikey`

### 4.5 交互向导脚本

```
$ tavern config init

Welcome to Tavern. Let's set up your LLM.

Which provider?
  1) anthropic    Claude models (recommended for Narrator)
  2) openai      GPT models
  3) deepseek    Cheap and fast — good for Extractor
  4) ollama      Local models (no API key needed)
  5) custom      Any OpenAI-compatible endpoint

Choice [1]: 1

Model [claude-sonnet-5]: 

API key (or leave blank to use $ANTHROPIC_API_KEY):
sk-ant-...

Configuration written to /Users/alice/.config/tavern/config.toml.
```

**交互鲁棒性**:
- 空输入接受默认值(方括号里的)
- Ctrl+C / Ctrl+D 应干净退出,不留半个 config.toml
- 非交互(stdin 非 tty)时:`init` 拒绝执行并提示"这是交互命令"

### 4.6 `show` 输出

```
$ tavern config show

config: /Users/alice/.config/tavern/config.toml

[llm.default]
  provider = "anthropic"
  model    = "claude-sonnet-5"
  api_key  = "sk-a...c3f2"       # 遮蔽

[llm.extractor]
  provider = "deepseek"
  model    = "deepseek-chat"
  api_key  = "sk-1...9def"

[ui]
  typewriter_speed_ms = 20
  color_scheme = "default"
```

`--reveal` 时打印完整值,顶部加 `⚠ REVEAL MODE — do not screenshot` 红字。

### 4.7 `check` 输出

```
$ tavern config check

✓ TOML syntax valid
✓ [llm.default] present
✓ provider = "anthropic" (recognized)
✓ model = "claude-sonnet-5"
✓ api_key present in config

Config OK.
```

错误示例:

```
$ tavern config check

✓ TOML syntax valid
✗ [llm.default].provider = "chatgtp" is not a recognized provider
     hint: valid providers are: anthropic, openai, deepseek, ollama, custom
⚠ [llm.default].api_key is empty and $ANTHROPIC_API_KEY is not set

Config has 1 error, 1 warning.
```

---

## 五、实现设计

### 5.1 模块结构

```
src/tavern/
├── cli.py                     ← 新增 config 子命令组
└── llmconfig/                 ← 新模块(避免与 stdlib 'config' 混淆)
    ├── __init__.py
    ├── schema.py              ← Config dataclass + PROVIDERS 常量
    ├── loader.py              ← 读 config.toml / 环境变量合并
    ├── writer.py              ← 交互向导 + 写 config.toml
    └── check.py               ← 校验规则 → Diagnostic 列表
```

**为什么叫 `llmconfig` 不叫 `config`**? `src/tavern/config.py` 已经用于文件系统布局(v0.2.0 引入),避免命名冲突。

### 5.2 依赖

**仍然 stdlib only**。`tomllib`(读)+ 手写 TOML 生成器(写,避免引入 `tomli-w`)。

### 5.3 关键 API

```python
# src/tavern/llmconfig/schema.py
@dataclass
class LLMRoleConfig:
    provider: str
    model: str
    api_key: str = ""
    base_url: str = ""
    api_key_from_env: bool = False    # runtime flag, set by resolver

@dataclass
class UIConfig:
    typewriter_speed_ms: int = 20
    color_scheme: str = "default"

@dataclass
class Config:
    llm: dict[str, LLMRoleConfig]   # {"default": ..., "extractor": ..., ...}
    ui: UIConfig

PROVIDERS: dict[str, ProviderMeta]

# src/tavern/llmconfig/loader.py
def config_path() -> Path                     # <tavern_home>/config.toml
def load_config() -> Config                   # 读盘 + 环境变量合并;文件不存在 → 空 Config
def load_config_raw() -> dict                 # 原始 TOML,不合并环境,供 check 用

# src/tavern/llmconfig/writer.py
def init_interactive(force: bool, provider_hint: str | None) -> Path
def write_config(cfg: Config) -> None

# src/tavern/llmconfig/check.py
def check_config(raw: dict) -> list[Diagnostic]    # 复用 diagnostics.Diagnostic
```

### 5.4 交互向导实现要点

- 用 `input()` + `sys.stdin.isatty()` 检测终端
- 每一步允许 Ctrl+C 中止(捕 `KeyboardInterrupt`, 打印 "Aborted." 退出码 1,**不写盘**)
- 写盘用 `.tmp` 临时文件 + `os.replace` 原子替换,防止半写状态
- 交互输出用 `sys.stdout.write` + `flush`,避免被 buffer 打断

### 5.5 TOML 生成

手写一个简单的 TOML dumper。理由:输入结构受控(我们生成,不是用户生成),只需要处理:
- 字符串(转义 `\` `"`,不需处理多行)
- int
- 表头 `[section]`

不引入 `tomli-w` 就是为了保持"零第三方依赖"。

### 5.6 校验规则

| ID | 规则 |
|---|---|
| C001 | TOML 语法错(报行号) |
| C002 | 缺 `[llm.default]` |
| C003 | `provider` 不在 PROVIDERS 里 |
| C004 | `model` 空(需要 model 的 provider) |
| C005 | `base_url` 对 custom provider 是必填 |
| Cw01 | `api_key` 空且对应 env var 也未设(need_key provider) |
| Cw02 | `[ui].typewriter_speed_ms` 不是 int / 不在 [0, 1000] |
| Cw03 | 存在未识别的段(可能拼错) |

### 5.7 环境变量合并语义

- 读盘得到 raw dict → 转 `Config` dataclass 时,若 `api_key == ""`,尝试从 `PROVIDERS[provider]["env_key"]` 读环境变量
- 读到:设 `api_key_from_env = True`,保留原值(不写回文件)
- 读不到:`api_key` 保持空;`check` 时给 Cw01 警告

---

## 六、测试策略

### 6.1 关键测试点

- `load_config` 在文件不存在时返回空 Config(不报错,方便 `init` 用户流程)
- 环境变量兜底:文件里 key 空 + env 有 → resolved 非空、`api_key_from_env=True`
- `mask_secret` 各种长度边界(0 / 4 / 8 / 20)
- 密钥字段识别(`api_key` / `apikey` / `AUTH_TOKEN` / `password`)
- TOML dumper 双引号 / 反斜杠转义
- `check` 每条规则的正负样本
- `init` 交互:用 `subprocess` + `input=...` feed
- `init --force` 覆盖已存在的 config
- 所有测试用 `tavern_home` fixture 隔离

### 6.2 不测

- 真实交互(TTY 检测)—— 需要伪 TTY,收益 < 成本
- 不测 provider 是否可达网络

---

## 七、风险与取舍

| 议题 | 决定 |
|---|---|
| 交互式向导 vs 声明式 `set key value`? | **交互式**。USAGE.md 承诺的是"3 问 3 答"体验;声明式接口不如让用户手动改 TOML |
| 密钥加密存储? | **不**。CLI 惯例是明文;想加密使用系统 keychain(如 `keyring` 库),归入 P4+ |
| 允许 `init` 时把 key 直接从 env 拷进文件? | **不**。env 变量存在时,让用户显式选"留空使用 env",避免密钥被无意 dump 到文件 |
| 多套 profile(dev/prod 切换)? | **不做**。用户可切换 `TAVERN_CONFIG_HOME` 达到同等效果 |
| `show` 默认遮蔽 vs 默认显示? | **默认遮蔽**。screenshot / paste 到 issue 场景很常见,默认安全 |

---

## 八、验收指标

- `tavern config init` 走通:选 provider → 填 model → 填 key → 落盘 → `tavern config check` 通过
- `tavern config show` 遮蔽输出、`--reveal` 才明文
- `ANTHROPIC_API_KEY=sk-test tavern config check`(config 里 key 空):不报 error,只 info 说"key 来自环境"
- 所有 4 个子命令都在 `tests/cli/test_config_command.py` e2e 覆盖
- 单元测试覆盖率 ≥ 85%(llmconfig/ 模块)

---

## 九、后续联动

- **P2.2 · LLM Provider 抽象**:直接消费 `load_config()` 拿到 `LLMRoleConfig`
- **P3 · orchestrator**:启动时 `check_config`,不 OK 就引导用户跑 `tavern config init`
- **未来 `tavern doctor`**:合并 `config check` + `validate 所有已装世界` + 网络 ping
