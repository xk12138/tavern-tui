# PRD · LLM Provider 抽象层 + `tavern play` 骨架

- 状态:草案 → 已实现
- 版本:v1.0
- 日期:2026-08-11
- 依赖:v0.3.0 交付的 `tavern.llmconfig`

---

## 一、问题陈述

v0.3.0 之后:世界装好了、密钥填好了 —— **玩家还是敲不动 `tavern`**。DESIGN.md §二 的四角色 LLM 架构、§九 M0 里程碑"Narrator + Extractor 双调用循环"都停在图纸上。

原因是缺**两块骨架**:

1. **LLM Provider 抽象层** —— 让 config.toml 里 `provider = "anthropic"` 真能对应到 `AnthropicProvider().complete(prompt)` 这样的调用。没有它,后续 Narrator/Extractor 无处可发。
2. **`tavern play <world-id>` 命令** —— 玩家的第一个可视界面。哪怕它现在只是"你输入 → GM 回一句话",也应先跑通,后续再逐步接上真正的 Narrator prompt。

### 为什么这轮同时做这两件

- Provider 抽象层单独发布,用户看不到进展 —— 没有调用点
- `tavern play` 单独发布,不接 provider 就是死循环
- 两件事情耦合度很低但**验收互为对方**:play 需要一个能收消息的东西,provider 需要一个真的能被调到的地方

**关键取舍**:引入一个 **EchoProvider** —— 它不发网络,只把玩家输入回显(带装饰)。这样:
- 用户装了 `provider = "echo"` 就能立刻**离线跑通** `tavern play`,不用花任何 API 额度
- 测试可以完整覆盖 `tavern play` 的输入循环,不需要真实网络
- AnthropicProvider 的**协议层**同样声明,但只做"能构造 HTTP 请求"这一层单元测试,不真发请求

### 影响

| 用户 | 痛点 |
|---|---|
| **玩家** | 手上一堆装好的东西却打不开门。EchoProvider + `tavern play` 让"敲 tavern 就能玩"的承诺兑现第一步 |
| **贡献者** | 后续接 OpenAI/DeepSeek/Ollama 只需实现 3 个方法,是"每添一家 provider 增量 <100 行"的地基 |
| **测试** | 有了 EchoProvider,Narrator/Extractor/orchestrator 都能在 CI 里跑,不依赖任何 API key |

---

## 二、目标与非目标

### 2.1 必须

1. **`LLMProvider` 抽象基类**,定义三个方法:`complete(prompt, **opts) -> str`、`stream(prompt, **opts) -> Iterator[str]`、`describe() -> str`(自检用)
2. **EchoProvider** —— 不发网络,把 prompt 的最后一段回显 + 装饰。**它是 v0.4.0 的默认演示后端**
3. **AnthropicProvider** —— 骨架 + 单元测试(用 stub HTTP transport 验请求头/正文,不真发)。**先接 anthropic 一家**,别的 provider 归入下一轮
4. **`load_provider(role: str = "default")`** —— 从 `tavern.llmconfig` 读 role 段,实例化对应 provider
5. **`tavern play <world-id>` 命令** —— 加载已装世界 + provider,进入 REPL 循环:
   - 展示 `initial_tavern.opening_hook`
   - 读一行输入 → 送 provider → 打印回复
   - `/quit` 退出;Ctrl+C 干净退出;Ctrl+D 视为 quit
6. **`echo` 作为 config 里 provider 的合法值**(在 PROVIDERS 里加一项)
7. 完整测试:抽象层契约、EchoProvider、AnthropicProvider 请求构造、play 命令(用 EchoProvider e2e)

### 2.2 非目标

- 不做 Extractor / Director / MemoryKeeper 双调用(只做 Narrator 单调用)
- 不做 SQLite 存档 —— play 是无状态的,退出即忘。存档是 M1
- 不做打字机效果 / TUI —— 纯 stdio。TUI 是 M2
- 不做 OpenAI / DeepSeek / Ollama / Custom provider —— 下一轮
- 不做世界选择器(直接接受 `<world-id>` 参数)
- 不做真正的 Narrator prompt 组装(§DESIGN 描述的完整上下文注入)—— play 现在只送一个简单的系统提示 + 玩家输入
- 不发真实 Anthropic 请求,不做端到端调用测试(需要 API key,归入 `tavern doctor`)

---

## 三、用户故事

### US-1:验证 tavern play 能跑
> "作为新用户,我 config init 选了 echo,tavern install 装了 minimal-tavern。现在 `tavern play minimal-tavern` 应该给我看到 opening_hook,然后等我输入。"

**验收**:
- 打印 opening_hook 段落
- 显示 `> ` 提示符
- 输入任意文本 → 回车 → GM 回复一段
- `/quit` 或 Ctrl+D 退出

### US-2:切换 provider 不重装
> "我改了 config.toml 里 provider 从 echo 到 anthropic,重启 tavern play 应该用新的 provider,不需要任何其他动作。"

**验收**:
- Provider 实例化只在 `tavern play` 启动时发生一次
- 换 provider 不影响世界包目录

### US-3:开发者添加新 provider
> "我想加 OpenAI provider。应该只需要写一个类,继承 LLMProvider,实现 3 个方法,注册到 provider registry。"

**验收**:
- provider 注册表以 dict 形式存在,新 provider 加一行即可
- 抽象基类文档清晰,能不看现有 provider 就知道要做什么

### US-4:世界包配置无效时的错误信息
> "我 `tavern play nonexistent-world` 应该报清楚错,不是 traceback。"

**验收**:
- world_id 找不到 → 退出 1,提示"use `tavern list` to see installed worlds"
- config 里没 `[llm.default]` → 退出 1,提示"run `tavern config init`"
- api_key 缺失(非 echo/ollama) → 退出 1,提示 env var / config 修法

### US-5:CI 场景
> "我想让 GitHub Actions 里 `tavern play minimal-tavern` 能跑一轮 smoke test,不烧 API 额度。"

**验收**:
- 用 EchoProvider + stdin 送一行 + `/quit`
- 全程无网络,退出码 0

---

## 四、功能规格

### 4.1 抽象接口

```python
# src/tavern/llm/base.py
class LLMProvider(Protocol):
    def complete(self, prompt: str, *, system: str = "", max_tokens: int = 1024) -> str: ...
    def stream(self, prompt: str, *, system: str = "", max_tokens: int = 1024) -> Iterator[str]: ...
    def describe(self) -> str:
        """One-line human-readable identifier, e.g. 'Anthropic claude-sonnet-5'."""
```

- **默认 stream 实现**:调 complete 后一次性 yield —— 方便快速实现新 provider,愿意做流式再覆盖
- **不引入 `abc.ABC`**:用 typing.Protocol 更松散,便于 duck typing

### 4.2 Provider 注册

```python
# src/tavern/llm/registry.py
PROVIDER_CLASSES = {
    "echo":      "tavern.llm.echo:EchoProvider",
    "anthropic": "tavern.llm.anthropic:AnthropicProvider",
    # openai / deepseek / ollama / custom — next round
}

def load_provider(role: str = "default") -> LLMProvider: ...
```

- 用**字符串导入路径**避免 `tavern.llm.__init__` 顶层就 import 所有 provider,启动更快
- `load_provider("default")` 会:
  1. 调 `tavern.llmconfig.load_config()`
  2. 拿 `config.llm[role]`(缺失 → fallback 到 default)
  3. 从 PROVIDER_CLASSES 查 provider name
  4. 动态 import + 实例化,注入 role_cfg

### 4.3 EchoProvider

```python
class EchoProvider:
    def __init__(self, cfg: LLMRoleConfig):
        self.cfg = cfg
    def complete(self, prompt: str, *, system: str = "", max_tokens: int = 1024) -> str:
        # Take the last user turn, decorate it as narrator would.
        last = prompt.rsplit("\n\nPlayer: ", 1)[-1].strip()
        return f"[echo] The world hears you: \"{last}\". Something stirs."
    def stream(self, prompt, **opts):
        yield self.complete(prompt, **opts)
    def describe(self) -> str:
        return "Echo (offline demo — does not call any LLM)"
```

- **足够诚实**:输出里带 `[echo]` 前缀,玩家立刻看出这不是真 GM
- **足够像 GM**:装饰一句让流程看起来通

### 4.4 AnthropicProvider

```python
class AnthropicProvider:
    """Calls the Claude Messages API.

    Kept minimal: no streaming, no tool use, no caching — those land later.
    """
    API_URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, cfg: LLMRoleConfig, *, transport=None):
        self.cfg = cfg
        self._transport = transport   # for injecting fakes in tests

    def _build_request(self, prompt: str, *, system: str, max_tokens: int) -> tuple[str, dict, dict]:
        """Return (url, headers, body) — no I/O, purely testable."""
        ...

    def complete(self, prompt, *, system="", max_tokens=1024) -> str:
        url, headers, body = self._build_request(prompt, system=system, max_tokens=max_tokens)
        # send via self._transport or urllib
        ...
```

- **key 来源**:实例化时若 `cfg.api_key` 为空,再看 `ANTHROPIC_API_KEY` env(重复 loader 的兜底,防止直接 `AnthropicProvider(cfg)` 被绕过)
- **无第三方依赖**:用 `urllib.request` 发 POST。测试时注入 `transport` 走假的
- **describe**:返回 `"Anthropic <model>"`

### 4.5 `tavern play <world-id>`

```
tavern play <WORLD_ID> [--provider ROLE]

  WORLD_ID    id of an installed world (see `tavern list`)
  --provider  which config role to use (default: "default")

Interaction:
  - Prints the world.initial_tavern.opening_hook as GM's opening line
  - Reads lines from stdin
  - Each non-command line is sent to the provider
  - `/quit`, `/exit`, Ctrl+D → clean exit
```

### 4.6 Play 会话交互设计

```
$ tavern play example-jianghu

── 江湖夜雨 · 醉仙楼 ──

你推门进来,酒香混着桂花的甜味扑面而来。
角落里,那个自称姓沈的说书人抬眼看了你一下,又低下头。
掌柜从吧台后面招手:"客官,今日想坐哪儿?"

(provider: Echo (offline demo — does not call any LLM))
(type /quit to exit)

> 走到角落去看看那个说书人

[echo] The world hears you: "走到角落去看看那个说书人". Something stirs.

> /quit
Goodbye.
```

- 首屏打印世界名 + 初始酒馆名(TS 分隔线)
- 然后 `opening_hook` 原文
- 括号里显示 provider.describe() —— 玩家知道自己在用什么后端
- 提示 `/quit`
- 循环:`> ` 提示 → 一行 → provider → 打印

### 4.7 错误路径

| 情况 | 退出码 | 提示 |
|---|---|---|
| WORLD_ID 未安装 | 1 | `world 'X' not installed. Run \`tavern list\` to see installed worlds.` |
| 已装但 `world.toml` 坏了 | 1 | `world 'X' is broken: <diagnostic>` |
| config.toml 缺 `[llm.default]` | 1 | `no [llm.<role>] configured. Run \`tavern config init\`.` |
| provider 名不在 registry | 1 | `unknown provider '<x>'. Valid: <list>` |
| Anthropic API 401/403 | 1 | `provider auth failed: <message>. Check your api_key.` |
| Anthropic 网络失败 | 1 | `provider request failed: <error>` |
| provider 抛未知异常 | 1 | full traceback with `TAVERN_DEBUG=1`,否则只打印 message |

### 4.8 依赖

**仍然 stdlib only**:
- `urllib.request` 发 HTTP
- `json` 编解码
- `typing.Protocol` 声明接口

---

## 五、实现设计

### 5.1 模块结构

```
src/tavern/llm/
├── __init__.py           ← 只 re-export load_provider
├── base.py               ← Protocol + LLMError
├── registry.py           ← PROVIDER_CLASSES dict + load_provider()
├── echo.py               ← EchoProvider
└── anthropic.py          ← AnthropicProvider
```

### 5.2 关键接口摘要

```python
# base.py
class LLMError(Exception): ...
class LLMAuthError(LLMError): ...
class LLMNetworkError(LLMError): ...

@runtime_checkable
class LLMProvider(Protocol): ...

# registry.py
def load_provider(role: str = "default", *, cfg: Config | None = None) -> LLMProvider: ...

# echo.py
class EchoProvider: ...

# anthropic.py
class AnthropicProvider: ...
```

### 5.3 Play 命令实现要点

```python
# in cli.py
def _cmd_play(args) -> int:
    # 1. locate world
    for w in list_installed():
        if w.id == args.world_id:
            world = w
            break
    else:
        error → 1

    # 2. load pack details
    pack = load_worldpack(world.path).pack

    # 3. build provider
    try:
        provider = load_provider(args.provider)
    except LLMError as e:
        error → 1

    # 4. print opening
    print(f"── {pack.world.name} · {pack.world.initial_tavern.get('name','?')} ──\n")
    print(pack.world.initial_tavern.get('opening_hook','...').strip())
    print(f"\n(provider: {provider.describe()})")
    print("(type /quit to exit)\n")

    # 5. REPL
    while True:
        try:
            line = input("> ").strip()
        except EOFError:
            print("Goodbye."); break
        if line in ("/quit", "/exit"): print("Goodbye."); break
        if not line: continue
        # simple prompt: system = world.rules.summary; user = last line
        try:
            reply = provider.complete(line, system=_system_prompt(pack))
        except LLMError as e:
            print(f"[error] {e}", file=sys.stderr); continue
        print(f"\n{reply}\n")

    return 0
```

### 5.4 `_system_prompt(pack)` 简化版

只把三段东西拼上,不做上下文管理(那是 orchestrator 的活):

```
You are the Narrator (GM) of a story set in the world "<name>".

World tone: <setting.tone>
World rules:
<rules.summary>

Respond in second person, present tense. Keep replies under 3 short paragraphs.
Do not break character.
```

### 5.5 EchoProvider 的实现细节

对当前 prompt 只提取"最后一句用户输入"来 echo。EchoProvider 的目标不是像 GM,而是**让流程动起来**并让玩家立即看到"输入被处理了"。

---

## 六、测试策略

### 6.1 抽象层契约测试

- `EchoProvider` 符合 `LLMProvider` Protocol(`isinstance(p, LLMProvider)` 用 `runtime_checkable`)
- `AnthropicProvider` 同上
- `describe()` 返回非空字符串
- `stream()` 默认实现:yield 一段等于 complete

### 6.2 EchoProvider

- 空输入不 crash
- 输入被回显在输出里
- 描述字符串包含 "Echo"

### 6.3 AnthropicProvider

- `_build_request(prompt, system, max_tokens)`:
  - URL = messages endpoint
  - Headers 包含 `x-api-key`、`anthropic-version`、`content-type: application/json`
  - Body JSON 里有 `model`、`max_tokens`、`system`、`messages=[{"role":"user","content":prompt}]`
- 注入一个 fake transport,验:
  - 200 响应正确解出 `content[0].text`
  - 401 响应抛 `LLMAuthError`
  - 网络异常抛 `LLMNetworkError`
- 无 api_key 时实例化就抛错

### 6.4 Registry

- `load_provider("default")` 从 config 找 provider name → 实例化正确类
- 未知 provider → 抛 LLMError
- role 不存在时 fallback 到 default

### 6.5 `tavern play` e2e(用 EchoProvider)

- 装 minimal-tavern → config 里 provider=echo → `tavern play minimal-tavern` 送 stdin
- 输入一行 + `/quit` → 输出里有 `[echo]` + `Goodbye`
- 输入 `/quit` 直接 → 干净退出
- Ctrl+D(stdin close) → 干净退出
- world_id 不存在 → 退出 1
- 无 config → 退出 1
- 所有 e2e 用 `TAVERN_CONFIG_HOME` 隔离

### 6.6 不测

- 真实网络到 Anthropic
- 交互流式 UI(TUI 是 M2)

---

## 七、风险与取舍

| 议题 | 决定 |
|---|---|
| 用 `Protocol` 还是 `abc.ABC`? | **Protocol**。松散、便于 duck typing、测试友好;`runtime_checkable` 保留 isinstance 能力 |
| Provider 是否 own key 兜底逻辑? | **是**。loader 层已做一次,provider 里再做一次(instance-level),防绕过 loader 的调用路径 |
| 用 `httpx` 还是 stdlib `urllib`? | **stdlib**。零依赖是本项目的核心约束;`urllib.request.Request` + `json` 足够 |
| 单例 provider 还是每次调用重建? | **每次 `load_provider` 重建**。GM 是无状态的,provider 也不该缓存;后续 orchestrator 可自行 memoize |
| EchoProvider 该不该做完整回声? | **只回声最后一句**。目标是"看得出流程通了",不是"看起来像 GM" |
| `tavern play` 出错要不要交互修复(比如"要不要现在 config init?")? | **不做**。UNIX 惯例是"打印指令,让用户自己下决定" |

---

## 八、验收指标

- `tavern play example-jianghu` 用 EchoProvider 能跑 5 轮输入
- `tavern play nonexistent` 退出 1,错误友好
- `tavern play example-jianghu` 无 config 时退出 1,提示跑 `config init`
- 所有测试 ≥ 90% 覆盖 llm/ 模块(除 anthropic 真网络分支)
- 总测试仍 <3 秒跑完

---

## 九、后续联动

- **P2.3 · OpenAI / DeepSeek / Ollama / Custom provider**:每个 <100 行,复用同一 Protocol
- **P3.1 · orchestrator**:替换 play 的 REPL,做真正的 Narrator+Extractor 双调用循环
- **P3.2 · 场景日志 + SQLite**:play 现在无状态,orchestrator 会挂上 scene_log 写入
- **M2 TUI**:play 命令是 REPL,TUI 版是给 REPL 换外壳
