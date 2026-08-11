# PRD · OpenAI / DeepSeek / Ollama / Custom Provider 实现

- 状态:草案 → 已实现
- 版本:v1.0
- 日期:2026-08-11
- 依赖:v0.4.0 的 `LLMProvider` 抽象;v0.3.0 的 `PROVIDERS` 元表
- 里程碑:M0 骨架补完 + 玩家 provider 覆盖面翻 4 倍

---

## 一、问题陈述

v0.3 起,`tavern config init` 就把 5 个 provider 选项(Anthropic / OpenAI / DeepSeek / Ollama / Custom)列在向导里。v0.4 只实现了 **Anthropic + Echo**。结果:

- 选 OpenAI / DeepSeek / Ollama / Custom → 向导写盘 → `tavern play` → `unknown provider 'openai'`
- 玩家没有 Anthropic API key 就**完全跑不动真实 LLM**

尤其**Ollama**:本地部署,免 API key,免费,是**新玩家零门槛入门**的关键。

DESIGN.md §七的 provider 抽象是"统一抽象层,可插拔:Anthropic / OpenAI / DeepSeek / Ollama / 任意 OpenAI 兼容接口"—— 现在把承诺兑现完。

### 影响

| 用户 | 痛点 |
|---|---|
| **无 Anthropic key 的玩家** | tavern 装了、config 配了,但真跑起来就报"unknown provider"—— 是**表面完成的假象** |
| **希望本地跑的玩家** | Ollama 是免费/隐私/离线的核心方案,现在唯一路径是自己写 Custom(还不存在) |
| **中国玩家** | DeepSeek 是最经济的国内选项,不接就等于把大量用户拒之门外 |
| **未来 Extractor** | 需要"便宜模型跑 JSON 提取"—— DeepSeek/Ollama 恰是首选 |
| **未来 `/export novel`** | 需要至少一个能真跑的 provider,当前只有 Anthropic |

### 为什么这轮做

- **独立可交付**:每家 <100 行,共享抽象基类,无 schema 变更、无 CLI 变更
- **完全可测**:所有 provider 走"注入 transport"路径,不发真实网络
- **覆盖 5 个 provider 中的 4 个**(Echo + Anthropic + 本轮 4 家 = 6 家 provider 全部就位)

---

## 二、目标与非目标

### 2.1 必须

1. **`OpenAIProvider`** —— 走 `POST /v1/chat/completions`
2. **`DeepSeekProvider`** —— 与 OpenAI 协议**兼容**,共享代码,只换 endpoint + env key
3. **`CustomProvider`** —— 任意 OpenAI 兼容 endpoint;`base_url` 必填;共享 OpenAI 代码
4. **`OllamaProvider`** —— 走 `POST /api/chat`,无 API key,`base_url` 默认 `http://localhost:11434`
5. **`registry.py` 注册**:补上 4 家 dotted path
6. **共享的 OpenAI 兼容基类** —— 抽出 `_OpenAICompatProvider`,让 OpenAI / DeepSeek / Custom 复用
7. **测试**:每家 provider 至少 3 个测试:
   - `_build_request` 的 URL / headers / body 结构
   - 注入 transport 走通 happy path,提取正确文本
   - 401/403 → `LLMAuthError`
8. **描述字符串** `describe()`:格式 `<Provider> <model>`,Ollama 加 `(local)` 后缀,Custom 显示 base_url 主机

### 2.2 非目标

- 不做流式 SSE(每家 provider 默认 `stream = default_stream`,单块产出)—— TUI 引入时再做
- 不做 tool use / function calling
- 不做 prompt caching(Anthropic 独有)
- 不发真实网络的集成测试
- 不做重试 / 退避策略(下一轮 `tavern doctor` 可考虑)
- 不做 tokenization 精确计费

---

## 三、用户故事

### US-1:用 Ollama 免费本地跑
> "作为新玩家,我不想付费。装了 Ollama,`ollama serve` 起来。`tavern config init` 选 4 (ollama) → default model qwen2.5:14b → 无需 API key。`tavern play` 跑通。"

**验收**:
- config init 选 Ollama 生成的 config 合法
- `tavern config check` 不报缺 key(Ollama needs_key=False,已存在)
- `AnthropicProvider` 一样的 fake transport 测试,验请求打到 `http://localhost:11434/api/chat`

### US-2:用 OpenAI GPT
> "我有 OPENAI_API_KEY。config init 选 2 → gpt-4o → 让 env 兜底 → `tavern play` 打得通。"

**验收**:
- Request 打到 `https://api.openai.com/v1/chat/completions`
- Headers 含 `Authorization: Bearer <key>` + `content-type: application/json`
- Body 是 OpenAI Chat 格式 `{model, messages:[{"role":"system","content":...},{"role":"user","content":...}], max_tokens}`

### US-3:走内网代理(One-API / 自建 gateway)
> "公司有 One-API 网关。用 Custom provider,base_url 填 https://our-gateway.internal/v1,api_key 填 gateway 的 key。"

**验收**:
- Custom provider 拒绝空 base_url(v0.3 已在 `check_config` 里处理,但 Custom Provider 实例化时也要防)
- Request 打到 `<base_url>/chat/completions`
- describe() 显示 `Custom (our-gateway.internal) <model>`

### US-4:DeepSeek 便宜
> "DeepSeek 便宜。config init 选 3。"

**验收**:
- Request 打到 `https://api.deepseek.com/v1/chat/completions`
- 其余同 OpenAI

---

## 四、功能规格

### 4.1 抽象共享层

在 `src/tavern/llm/openai_compat.py` 引入基类 `_OpenAICompatProvider`,3 家 provider 共享:

```python
class _OpenAICompatProvider:
    BASE_URL = ""              # subclass overrides
    DEFAULT_MODEL = ""
    ENV_KEY = ""               # optional, for env-var fallback
    DISPLAY_NAME = "OpenAI"
    NEEDS_KEY = True

    def __init__(self, cfg, *, transport=None):
        # base_url from cfg.base_url or BASE_URL
        # api_key from cfg.api_key or ENV_KEY env
        # raise LLMAuthError if NEEDS_KEY and key still empty

    def _endpoint(self) -> str:
        return self._base_url.rstrip("/") + "/chat/completions"

    def _build_request(self, prompt, *, system, max_tokens): ...
    def complete(self, prompt, *, system="", max_tokens=1024): ...
    def stream(self, prompt, **opts): return default_stream(self, prompt, **opts)
    def describe(self): ...
```

具体子类:

```python
class OpenAIProvider(_OpenAICompatProvider):
    BASE_URL = "https://api.openai.com/v1"
    DEFAULT_MODEL = "gpt-4o"
    ENV_KEY = "OPENAI_API_KEY"
    DISPLAY_NAME = "OpenAI"

class DeepSeekProvider(_OpenAICompatProvider):
    BASE_URL = "https://api.deepseek.com/v1"
    DEFAULT_MODEL = "deepseek-chat"
    ENV_KEY = "DEEPSEEK_API_KEY"
    DISPLAY_NAME = "DeepSeek"

class CustomProvider(_OpenAICompatProvider):
    BASE_URL = ""           # forces cfg.base_url
    DEFAULT_MODEL = ""      # forces cfg.model
    ENV_KEY = ""            # no env fallback for custom
    DISPLAY_NAME = "Custom"

    def __init__(self, cfg, *, transport=None):
        if not (cfg and cfg.base_url):
            raise LLMError("Custom provider requires base_url in config")
        if not (cfg and cfg.model):
            raise LLMError("Custom provider requires model in config")
        super().__init__(cfg, transport=transport)

    def describe(self):
        host = urlparse(self._base_url).netloc or self._base_url
        return f"Custom ({host}) {self._model}"
```

### 4.2 OpenAI-compat request 结构

```python
url = "<base_url>/chat/completions"
headers = {
    "Authorization": f"Bearer {api_key}",
    "content-type": "application/json",
}
body = {
    "model": model,
    "max_tokens": max_tokens,
    "messages": [
        # system message optional
        {"role": "system", "content": system} if system else None,
        {"role": "user", "content": prompt},
    ],
    # DROP the None if no system
}
```

响应结构:
```json
{
  "choices": [
    {"message": {"role": "assistant", "content": "hi there"}}
  ]
}
```

提取:
```python
data["choices"][0]["message"]["content"]
```

出错分支:
- HTTP 401/403 → `LLMAuthError`
- HTTP 其他 → `LLMError`
- URLError → `LLMNetworkError`
- JSON 解析失败 → `LLMResponseError`
- content 缺失/为空 → `LLMResponseError`

### 4.3 Ollama provider

Ollama 的 API 与 OpenAI **不完全兼容**(有 `/v1/chat/completions` 兼容层但 Ollama 官方推荐 `/api/chat`)。

选择 `/api/chat` 让原生。

```python
class OllamaProvider:
    DEFAULT_BASE_URL = "http://localhost:11434"
    DEFAULT_MODEL = "qwen2.5:14b"

    def __init__(self, cfg, *, transport=None):
        self._base_url = (cfg.base_url if cfg and cfg.base_url else self.DEFAULT_BASE_URL)
        self._model = (cfg.model if cfg and cfg.model else self.DEFAULT_MODEL)
        # no api_key needed

    def _endpoint(self) -> str:
        return self._base_url.rstrip("/") + "/api/chat"

    def _build_request(self, prompt, *, system, max_tokens):
        body = {
            "model": self._model,
            "messages": [...],
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        return self._endpoint(), json.dumps(body).encode(), {"content-type": "application/json"}

    def complete(...):
        data = self._call(...)
        return data["message"]["content"]

    def describe(self):
        return f"Ollama {self._model} (local)"
```

响应:
```json
{"model": "...", "message": {"role":"assistant","content":"hi"}, "done": true}
```

**Ollama 无 auth**,所以不产 `LLMAuthError`。网络失败仍 → `LLMNetworkError`。

### 4.4 Registry 更新

```python
PROVIDER_CLASSES: dict[str, str] = {
    "echo":      "tavern.llm.echo:EchoProvider",
    "anthropic": "tavern.llm.anthropic:AnthropicProvider",
    "openai":    "tavern.llm.openai_compat:OpenAIProvider",
    "deepseek":  "tavern.llm.openai_compat:DeepSeekProvider",
    "custom":    "tavern.llm.openai_compat:CustomProvider",
    "ollama":    "tavern.llm.ollama:OllamaProvider",
}
```

### 4.5 CLI / config 行为无变

`tavern config init` 已能列 6 个 provider(Echo 是 v0.4 加的)—— 本轮不改 CLI。

### 4.6 依赖

**stdlib only** —— `urllib.request` + `json` + `urllib.parse.urlparse`(为 Custom.describe)。

---

## 五、实现设计

### 5.1 模块结构

```
src/tavern/llm/
├── base.py              (existing, 未变)
├── echo.py              (existing, 未变)
├── anthropic.py         (existing, 未变)
├── openai_compat.py     ← 新:共享基类 + OpenAI / DeepSeek / Custom
├── ollama.py            ← 新
└── registry.py          ← 修:补 4 行
```

### 5.2 共享 `_urllib_transport` 逻辑

`anthropic.py` 现有 `_urllib_transport` 是 module-private。**抽到 `base.py`**(或新的 `_http.py`)供多家复用。为了不破坏 anthropic.py 的现状,新建 `src/tavern/llm/_http.py`,anthropic.py 迁移过来 import。

**取舍**:把 anthropic.py 迁一小步(内部函数改 import),影响面小、测试还是绿。

### 5.3 错误映射一致性

401/403 → LLMAuthError
其他 HTTP → LLMError(带 `HTTP N: <body>`)
URLError → LLMNetworkError
JSON 错 → LLMResponseError

全部走 `_http.urllib_transport()` 统一处理。

### 5.4 `describe()` 规范

| Provider | describe() |
|---|---|
| OpenAI | `OpenAI <model>` |
| DeepSeek | `DeepSeek <model>` |
| Custom | `Custom (<host>) <model>` |
| Ollama | `Ollama <model> (local)` |

### 5.5 base_url 归一化

- 用户可能填 `https://api.openai.com/v1` 或 `https://api.openai.com/v1/`
- endpoint 拼接前 `rstrip("/")`,再加 `/chat/completions`
- 用户如果误填 `https://api.openai.com`(缺 `/v1`)—— 是他的锅,报 HTTP 404 时清楚
- 用户如果误填 `https://api.openai.com/v1/chat/completions` —— 会拼到 `.../chat/completions/chat/completions`,报 404。同理不救

### 5.6 测试隔离

- 所有 provider 测试用注入 `transport=fake_fn`,不走 urllib
- 每个 provider 至少一个测试**验请求打到正确的 URL**
- Ollama 测试单独一份文件

---

## 六、测试策略

### 6.1 单元测试

`tests/llm/test_openai_compat.py`:
- OpenAI: build_request URL + Bearer + body shape
- OpenAI: happy path extraction
- OpenAI: 401 → LLMAuthError
- OpenAI: system prompt inclusion / omission
- DeepSeek: URL / env key / describe
- Custom: 空 base_url 抛;空 model 抛;describe 含 host
- Custom: 允许 env 变量兜底吗? **不允许**(ENV_KEY="",cfg.api_key 必填。Custom user 自己知道 key 在哪)

`tests/llm/test_ollama.py`:
- build_request URL 是 `<base_url>/api/chat`
- 无 API key 也能实例化
- 网络失败 → LLMNetworkError
- describe 含 "local"
- 使用默认 base_url

### 6.2 契约测试

`tests/llm/test_registry.py` 已存在,补几个新用例:
- `load_provider("openai" | "ollama" | "deepseek" | "custom")` 能实例化(有合适 cfg)
- Custom 缺 base_url → LLMError(不是 unknown provider)

### 6.3 目标

- 每家 provider 覆盖率 ≥ 85%
- 总测试仍 <6 秒跑完

---

## 七、风险与取舍

| 议题 | 决定 |
|---|---|
| OpenAI 和 DeepSeek / Custom 共享基类 vs 各写各的? | **共享基类**。三者协议一致,减重复;子类只覆盖常量 |
| 抽出 `_http.py` 供多家复用? | **是**,避免每家重写 401/403 分支 |
| Ollama 走 `/v1/chat/completions` 兼容层 vs `/api/chat`? | **`/api/chat`**。Ollama 官方推荐;兼容层可能滞后 |
| Ollama 需要 base_url 校验(拒空)吗? | **不**。默认 localhost:11434,空 = 默认 |
| Custom 是否允许 env fallback? | **不**。用户显式选 custom 就应完整给出 key;env 兜底会让"忘填 key"更难发现 |
| 是否兼容 Azure OpenAI(不同 auth header + 路径)? | **不**。属于 Custom 场景,用户可写 Azure gateway 或用 One-API 转发 |
| stream=False on Ollama? | **是**。默认非流式(和其他 provider 一致);未来做流式再改 |

---

## 八、验收指标

- `tavern config init` 选任一 provider(除 anthropic)→ `tavern config check` 不报未知 provider
- `AnthropicProvider` 现有测试全绿(重构 `_urllib_transport` 不影响)
- 每家 provider 3+ 个单元测试
- 覆盖率:openai_compat ≥ 85%,ollama ≥ 85%
- `PROVIDER_CLASSES` 里所有 provider 都能被 `load_provider` 成功实例化(用合法 cfg)

---

## 九、后续联动

- **`tavern doctor`**(未来)—— 遍历所有 provider,尝试小 request,报 ok/timeout/auth failed
- **Extractor(下一轮)**—— 用 DeepSeek 便宜提取 state_delta
- **`/export novel`** —— 用配好的 provider,读 save.turns(),LLM 重写小说
