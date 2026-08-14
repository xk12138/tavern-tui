# CHANGELOG

本项目遵循 [Keep a Changelog](https://keepachangelog.com/) 与 [SemVer](https://semver.org/) 精神。

## [0.9.0] · 2026-08-14 · 场景建议(Suggestions)

**主题**:治"玩家迷茫"。GM 回复后展示一组**玩家第一人称**的建议台词,支持 **Claude Code 式的交互选择**(↑/↓ 方向键 + 绿色高亮 + 回车采用),列表末尾固定一个"说点什么"自由输入出口。建议是提示,不是轨道 —— 打字或选择"说点什么"随时回到自由输入。

### 新增

- **`tavern.roles.suggester` 角色** `src/tavern/roles/suggester.py`
  - `Suggestion(kind, text)` —— kind ∈ say/think/action,text 是玩家第一人称台词
  - `suggest()` —— 读最近 GM 回合 + 玩家风格参考,一次轻量 LLM 调用产出 ≤3 条建议;**永不抛异常**,失败自动回退世界包静态建议
  - `static_suggestions()` —— 解析 `[[world.initial_tavern.suggestions]]`(世界作者手写,运行时优先)
  - `suggestion_to_raw()` —— say→`"…"` / think→`*…*` / action→原文,直接复用 `parse_input` 管道
- **交互式建议选择**(`tavern.repl.lineedit`)
  - `readline_wide(..., choices=...)` 进入建议选择模式:渲染编号列表,↑/↓ 移动绿色高亮,回车采用
  - 末位固定 `[N] 说点什么…`(浅灰)= 自由输入出口
  - **打字不清列表**:第一个可打印字符(含中文)按下时,高亮自动跳到"说点什么"并变绿,字符进入 `>` 提示行;列表常驻,回车才提交 —— 回车有输入提交输入、无输入提交当前高亮选项
  - 退格编辑输入;Ctrl-C/Ctrl-D 语义与普通输入一致
  - 重绘逐行 `\r` + 整行擦除(`\033[2K`),左缘固定对齐,不残留错位;`NO_COLOR` 下无颜色码
  - 非 TTY(管道/CI)降级:打印纯文本列表,`[N]`/`:N` 输入选择兜底
- **REPL 集成**(`cli.py`)
  - **开局即推荐**:第一个提示符出现前就做一次 Suggest 调用(以 opening_hook 为上下文),静态建议仍优先、失败回退 —— 世界作者没写静态建议时玩家开局也有推荐
  - GM 回复后自动刷新建议列表;返场也先刷新
  - `[1]`/`[2]`/`[3]` 与 `:1`/`:2`/`:3` 键入选择;`[N]` 指向"说点什么"时交还自由输入;越界提示 `[no suggestion N]` 不送 GM
  - `/hint` 手动刷新 · `/hint off|on` 会话开关
  - `[ui] suggestions = false` 永久关闭(默认 true)
- **配置**:`LLM_ROLES` 增加 `suggest` 角色(`[llm.suggest]` 可配便宜模型,缺省 fallback default);`UIConfig.suggestions`
- **世界包校验**:新增 `W010`(suggestions 条目 kind 非法 / text 缺失)
- **文档**:USAGE.md §五(交互选择)、§六(`/hint`)、WORLD_BUILDING.md §2.6(静态建议字段)

### 变更

- `tavern --version` → `tavern 0.9.0`
- `tavern play` 每回合(非 `/` 指令)多一次轻量 Suggest 调用,输出 ~200 token;**失败零影响**,不影响玩家已看到的 GM 回复
- **修复:Suggest 调用 max_tokens 4096 → 32768,拒绝时自动降级重试 4096** —— 推理型模型(DeepSeek R1/V4、o1 等)思维链会吃光小预算导致建议永远为空;32768 给足思维链空间,遇到设上限的端点(gpt-4o 16k / DeepSeek chat 8k / Anthropic Opus 32k)自动用 4096 重试一次,大值被拒不会拖垮整个功能
- **修复:suggest() 捕获任意异常而非仅 LLMError** —— 彻底兑现"永不抛异常、失败回退静态"
- **修复:建议列表重绘 off-by-one** —— `_redraw`/`_clear_block` 光标上移多了一行(`len(choices)+1` 应为 `len(choices)`):列表不在屏幕顶端时,每次按 ↑/↓ 列表整体上移一格、旧的 `> ` 提示行残留堆积、逐渐盖住上方原文。已修正,并用虚拟终端模拟器加回归测试(旧代码下 `> ` 堆积 4 行,断言恰好 1 行)
- **开局提示**:首次建议生成前打印 `(preparing suggestions…)`,推理模型慢时不至于让玩家对着冻结画面
- `lineedit.py` 的方向键处理:CSI/SS3 的 ↑↓ 从"吞掉"改为向建议模式暴露为令牌;普通输入行模式下仍被吞掉,不污染缓冲区
- `/help` 新增 Suggestions 分组

### 测试

- 新增 45 个测试(330 → 375):suggester 单测 13 个、lineedit 建议模式纯逻辑 15 个 + PTY 5 个、validator W010 3 个、llmconfig 5 个、CLI e2e 10 个
- 关键回归守卫:**选中 say 建议后存档存原文带引号、重放还原为 say**;打字跳到"说点什么"且列表常驻(transcript 断言重渲染);`[N]` 指向"说点什么"不送 GM;越界选择不送 GM;`/hint off` 后回合无建议列表;选项行左缘固定对齐;PTY 下方向键导航/回车采用/打字提交

### 设计取舍

- **第一人称台词,而非第三人称建议** —— 建议就是玩家自己可能说出口的话,所见即所选、选中即所存(存档存台词原文,小说导出/rewind 零改动)
- **打字不清列表** —— 输入即选中"说点什么"并变绿,列表常驻到回车;回车"有输入提交输入、无输入提交高亮项"。避免"刚想打字列表就消失"的割裂感,也保留"随时能选"的菜单感
- **逐行整行擦除渲染** —— 每次重绘 `\r` + `\033[2K`,列表左缘固定,杜绝残留碎片造成的错位
- **独立 Suggest 角色,不让 Narrator 顺带输出** —— 与 DESIGN.md"Narrator 专注创作、结构化输出走独立角色"一致
- **静态优先 + 动态补足** —— 世界作者手写质量最高,占位优先;LLM 负责覆盖演化场景
- **T: 心声类克制** —— prompt 限制最多 1 条,替玩家"想"最容易被滥用
- **失败静默回退** —— Suggest 是增强不是依赖,GM 回复已打印,建议失败不该打扰玩家

### 已知限制 & 后续

- 拖沓(节奏)问题未治 —— `plot_pacing` 运行时仍未被消费,归入未来 Director-lite
- 未做建议历史/撤回;选中后立即执行,无"预览再改"步骤
- 建议基于最近回合 + 世界设定,不感知玩家长期目标(Extractor/state_delta 落地后可注入)
- 非 TTY 会话无方向键交互(只打印列表 + `[N]` 输入选择)

### 里程碑对齐

- **M0(骨架跑通)**:80%(保持)
- **M1(状态与记忆)**:55%(保持)

---

## [0.8.0] · 2026-08-11 · 输入前缀语法 + 观察指令

**主题**:兑现 USAGE §五 §六 承诺 —— `"..."` `*...*` `:xxx` 前缀语法就位,5 个观察指令(`/where` `/who` `/inv` `/status` `/relations`)上线。玩家沉浸感的关键一环。

### 新增

- **`tavern.repl` 子系统** `src/tavern/repl/`
  - `parser.py` —— `parse_input()` + `Intent` + `SHORTCUT_MAP` + `INPUT_SYNTAX_PROMPT`
  - `observe.py` —— 5 个纯函数 `render_where / render_who / render_inv / render_status / render_relations`
  - `__init__.py` —— re-export 公共 API
- **输入前缀解析**
  - `"..."` → `Intent(kind="say")`,LLM 收到 `Player says (aloud): "..."`
  - `*...*` → `Intent(kind="think")`,LLM 收到 `Player thinks (internal, unheard by others): "..."`
  - `:xxx` → `Intent(kind="shortcut")`,查 `SHORTCUT_MAP` 展开;未知 shortcut 透传
  - `/xxx` → `Intent(kind="slash")`,不送 LLM
  - 其他 → `Intent(kind="action")`,默认
  - 未闭合前缀(`"hello`)→ 降级为 action
- **`SHORTCUT_MAP`** —— 6 个常用 shortcut:`look / wait / rest / inventory / map / recap`
- **观察指令 `/where` `/who [name]` `/inv` `/status` `/relations`**
  - `/where`:优先 `save.state.current_scene`,fallback 世界包 `initial_tavern`
  - `/who`:无参列 `present_npcs`;有参按 id/name/alias 精确+大小写不敏感匹配
  - **`/who` 显式过滤 `goals` / `secrets`**(GM 侧信息不泄漏给玩家)
  - `/inv` `/relations`:诚实标注"not tracked yet — Extractor coming"
  - `/status`:显示 save 层能拿到的(turn/day/time/scene),标注 HP/attributes 未追踪
- **REPL 集成**
  - `_run_play_loop` 用 `parse_input` 分派意图
  - `save.append_turn("player", intent.raw, ...)` —— **持久化 raw**,不是 llm_line。理由:novel export + rewind + replay 都需要玩家真实输入
  - Provider 收到 `intent.llm_line`,包含语义前缀
  - `_build_system_prompt` 追加 `INPUT_SYNTAX_PROMPT` —— 显式告诉 GM "internal 是私有的",防止 NPC 意外"听到"心声
- **`/help` 输出全面重排** —— 分组 Input syntax / Observation / Save / Other,更易读

### 变更

- `tavern --version` → `tavern 0.8.0`
- Save 里 `player` role 的 turn 记录格式**未变**(仍存玩家原文),向后兼容 v0.5+ 存档

### 测试

- 新增 48 个测试(246 → 294):
  - `tests/repl/test_parser.py`(22)—— 5 种意图 × 边界(空/未闭合/单字符),shortcut map 全覆盖,llm_line 格式快照
  - `tests/repl/test_observe.py`(15)—— 每个 render 函数正常 + 边界;**`test_who_never_leaks_goals_or_secrets`** 显式守护安全边界
  - `tests/cli/test_play_prefix_and_observe.py`(11)—— REPL 端到端,验证 provider 收到翻译后的 llm_line、save 存 raw、`/who` 不泄漏
- 覆盖率:parser **100%**,observe **98%**,__init__ **100%**
- 全 294 测试 9 秒跑完

### 设计取舍

- **save 存 raw 而非 llm_line** —— 玩家真敲的是"你好"不是"Player says: 你好";导出小说时 raw 更真;llm_line 是运行时衍生,不该持久化
- **未知 shortcut 透传** —— 让世界作者可以在世界包里约定自己的 shortcut,`SHORTCUT_MAP` 只是默认,不是硬编码白名单
- **前缀必须首尾匹配** —— `"未闭合` 降级为 action,而不是识别为 say;keep it simple,不做 escape
- **`INPUT_SYNTAX_PROMPT` 显式喂 GM** —— 只靠 `Player thinks (internal):` 不够,加一句"do NOT let other characters hear"锁死语义
- **`/who` 硬拒 goals/secrets** —— 有专门 regression test 守护;这是 GM 侧信息,玩家不该看到
- **观察指令不发 LLM** —— 是"UI 层读已知数据",不是"问 GM"。玩家想 IC 问 NPC 应该用 `"沈先生,你从哪来?"`
- **`repl/` 独立包** —— CLI 已 500+ 行;REPL 逻辑抽出去,cli.py 恢复"dispatch + 编排"职责
- **`/inv` `/relations` 诚实"未追踪"** —— 宁可少数据,不假数据(会误导玩家以为已追踪)

### 已知限制 & 后续

- 未实现 `/journal` `/wiki`(需事件日志 / 世界包 glossary)
- 未实现 `/tavern` 回酒馆软锚点(需场景切换机制)
- 未实现输入历史(↑/↓)—— 依赖 readline / TUI
- 未实现前缀 escape(`\"...\"`)—— 暂无实际需求
- Extractor 落地后 `/status` `/inv` `/relations` 才真的有数据 —— 现在只是指令位就位

### 里程碑对齐

- **M0(骨架跑通)**:80%(保持)
- **M1(状态与记忆)**:40% → **55%**(输入前缀 + 5 个观察指令铺位,Extractor 落地时直接接入)
- **M2(TUI 增强)**:0%(未启)

---

## [0.7.0] · 2026-08-11 · `/export novel` 小说导出

**主题**:玩家的"作品输出"路径。从 turn 日志到可分享的 markdown 小说。DESIGN 决策 J & M3 里程碑的核心承诺兑现。

### 新增

- **`tavern.export` 子系统** `src/tavern/export/`
  - `paths.py` —— `novels_home()` + `default_output_path()`,支持 `$TAVERN_NOVELS_HOME` 覆盖
  - `novel.py` —— `export_novel()` 引擎:配对 turn → 分块 → LLM 重写 → 拼接输出
  - `__init__.py` —— re-export 公共 API
- **顶层命令 `tavern export novel <save-name>`**
  - `--output PATH` 指定输出路径(默认 `~/tavern-novels/<save>-<timestamp>.md`)
  - `--provider ROLE` 指定 LLM role(默认:`export` role 存在则用,否则 fallback `default`)
  - `--force` 覆盖已存在的输出文件
- **REPL 内 `/export novel [PATH]`** —— play 会话里可用,复用当前 provider,导出后继续玩
- **输出格式**
  - YAML front matter:`title / world / save / turns / provider / generated_at / tavern_version`
  - 世界名作为 h1
  - 世界包 `intro.md` 或 `world.description` 作为背景引言
  - LLM 生成的小说正文
  - 中文 footer 标注生成信息
- **分块策略**
  - 阈值 5000 字符;超过则按 turn 对拆块
  - 续块 prompt 携带前一块最后 300 字作为上下文桥接
  - `ExportResult.chunk_count` 反映实际调用次数
- **Prompt 设计**
  - System:声明"改编 interactive story 为 prose fiction",指定世界/tone,列 5 条硬约束(第三人称过去时、不发明剧情、不破第四堵墙、用世界 tone、只输出正文)
  - 首块 user prompt 包含 `Opening scene:`;续块加上 `This is a continuation. Here is the last paragraph you wrote:`
- **公开 Python API**
  ```python
  from tavern.export import (
      export_novel, ExportResult, ExportError,
      novels_home, default_output_path,
  )
  ```
- **文档**
  - `docs/PRD-export-novel.md` —— 本次功能的 PRD

### 变更

- `tavern --version` → `tavern 0.7.0`
- CLI 帮助包含 `export` 子命令组
- REPL `/help` 输出新增 `/export novel [PATH]` 行

### 测试

- 新增 35 个测试(211 → 246):
  - `tests/export/test_paths.py`(4)—— novels_home 默认/覆盖,timestamp 格式,sanitize 坏字符
  - `tests/export/test_novel.py`(19)—— `_pair_turns` / `_build_chunks` / `_last_paragraph` 边界;端到端 export_novel(Echo)包括:空存档、target-exists、force、无 world_pack、多块、只读性验证
  - `tests/cli/test_export_command.py`(12)—— 顶层 + REPL 端到端,覆盖 provider role fallback、explicit role、`--output`、`--force`、错误路径
- 覆盖率:export/novel **97%**,paths/init **100%**,均超 90% 目标
- 全 246 测试 6.75 秒跑完

### 设计取舍

- **`~/tavern-novels` 而非 tavern_home 子目录** —— 小说是"给外面看的内容"(iCloud / 邮件 / 分享),独立于引擎 config;`$TAVERN_NOVELS_HOME` 覆盖用于测试与容器
- **默认分块 threshold=5000 字符** —— 保守;避免小模型 truncation。单块能塞下也走同一路径(chunk_count=1)
- **续块 tail 上下文 = 300 字** —— 够 LLM 承接语气,不占太多 token 预算
- **provider 优先级 `export → default`** —— USAGE §十一疑难解答明文承诺,支持"小说导出用便宜模型"
- **只读导出** —— 不改存档;`save.turns()`/`save.state` 前后一致(有回归测试守护)
- **`system` turn 处理**:第一条作为 `Opening scene:`,其余忽略。opening_hook 是玩家看到的第一段,理应进小说;其他 system 是引擎内部注入,不该出现在小说里
- **_REPL_PROVIDER module-level 变量** —— REPL slash-handler 需要 provider 但不想改 `_handle_slash` 的签名(会波及所有 handler)。可接受的胶水
- **不做 LLM 生成标题** —— 用世界名作 h1;LLM 标题风格不可控,增加不确定性
- **首版单一风格(第三人称过去时)** —— 未来 `--style` 参数位预留;首版先证明链路

### 已知限制 & 后续

- 未实现分章节(`--chapters`)
- 未实现单调用强制(`--single-shot`)
- 未实现风格切换(`--style novel|script|first-person|...`)
- 未实现 novel 索引(`tavern novels` 列已导出文件)
- 未加入 Extractor state_delta 到 prompt(小说会更有张力,但依赖 Extractor 落地)
- 分块之间的风格漂移不可避免;真实 provider 尚未测过(测试都用 Echo)
- 无真实网络端到端测试(需要 API key)

### 里程碑对齐

- **M0(骨架跑通)**:80%(保持)
- **M1(状态与记忆)**:40%(保持)
- **M3(长期记忆 + 渐进推进 + 小说导出)**:**30%**(小说导出交付,余下的是长期记忆、Director、多场景切换)

---

## [0.6.0] · 2026-08-11 · OpenAI / DeepSeek / Ollama / Custom Provider

**主题**:兑现 `PROVIDERS` 元表里承诺的 4 个 provider,让"无 Anthropic key 就跑不了"成为过去。M0 骨架的 provider 层补齐。

### 新增

- **`OpenAIProvider`** —— Chat Completions API(`POST /v1/chat/completions`)
  - `Authorization: Bearer <key>` + JSON body
  - `OPENAI_API_KEY` 环境变量兜底
  - 支持自定义 `base_url`(内网 gateway 场景)
- **`DeepSeekProvider`** —— OpenAI 协议兼容,endpoint `https://api.deepseek.com/v1`
  - `DEEPSEEK_API_KEY` 环境变量兜底
- **`CustomProvider`** —— 任意 OpenAI 兼容 endpoint
  - `base_url` 必填(实例化时校验,不只依赖 `config check`)
  - `model` 必填
  - **不允许 env fallback**(用户显式选 custom 就应完整给出 key)
  - `describe()` 显示 host,便于识别
- **`OllamaProvider`** —— 本地 Ollama(`POST /api/chat`)
  - 无 API key 需求
  - `base_url` 默认 `http://localhost:11434`
  - `describe()` 加 `(local)` 标记
- **共享代码抽取**
  - `src/tavern/llm/_http.py` —— `urllib_transport(url, body, headers)`,统一 HTTP 层
    - 401/403 → `LLMAuthError`
    - 其他 HTTP → `LLMError`
    - URLError → `LLMNetworkError`
    - JSON 解析失败 → `LLMResponseError`
  - `src/tavern/llm/openai_compat.py::_OpenAICompatProvider` —— OpenAI/DeepSeek/Custom 共享基类
    - 子类只覆盖 `BASE_URL / DEFAULT_MODEL / ENV_KEY / DISPLAY_NAME / NEEDS_KEY` 常量
    - 一处修好协议,三家同步
- **`registry.PROVIDER_CLASSES` 完整**
  ```python
  {
      "echo":      "tavern.llm.echo:EchoProvider",
      "anthropic": "tavern.llm.anthropic:AnthropicProvider",
      "openai":    "tavern.llm.openai_compat:OpenAIProvider",
      "deepseek":  "tavern.llm.openai_compat:DeepSeekProvider",
      "custom":    "tavern.llm.openai_compat:CustomProvider",
      "ollama":    "tavern.llm.ollama:OllamaProvider",
  }
  ```
- **`AnthropicProvider` 重构**(向后兼容)
  - 内部 `_urllib_transport` 迁移到 `_http.py`
  - 所有 10 个现有测试全绿,无行为变化
- **文档**
  - `docs/PRD-more-providers.md` —— 本次功能的 PRD

### 变更

- `tavern --version` → `tavern 0.6.0`
- **无 CLI 变更** —— `tavern config init` 早就列出 6 个 provider,现在选任一个都能真跑

### 测试

- 新增 31 个测试(180 → 211):
  - `tests/llm/test_openai_compat.py`(19)—— OpenAI/DeepSeek/Custom 三家的构造、请求结构、错误分支、env 兜底、happy path
  - `tests/llm/test_ollama.py`(9)—— 无 key、请求结构、默认 base_url、错误分支
  - `tests/llm/test_registry.py`(+5)—— 4 家新 provider 通过 registry 加载,Custom base_url 缺失报错
- 覆盖率:openai_compat **97%**、ollama **98%**、registry 96%,均超 85% 目标
- Anthropic 74% 保持不变(重构未回归)
- 全 211 测试 5.5 秒跑完

### 设计取舍

- **共享基类 vs 每家独立** —— 共享。协议一致 = 一处修 = 三家同步;子类只有 5 行常量,认知负担极低
- **抽出 `_http.py`** —— 避免 4 个 provider 各写一份 401/403 分支;Anthropic 也迁移过来
- **Ollama 走 `/api/chat` 而非 `/v1/chat/completions` 兼容层** —— 官方推荐 + 更接近原生行为
- **Custom 不允许 env 兜底** —— 若允许则用户误设 `OPENAI_API_KEY` 时会拿去打自己的 gateway(错的 key)。**显式 > 隐式**
- **Custom `describe()` 显示 host** —— 玩家启动时能一眼看清"我在往哪打";内网 gateway 场景友好
- **无流式 SSE** —— 每家默认 `default_stream` 单块产出;M2 TUI 引入时统一实现
- **保持 stdlib only** —— 依然无第三方 HTTP 库

### 已知限制 & 后续

- 未实现 Anthropic prompt caching / tool use(v0.4 起就非目标)
- 未实现流式 SSE(TUI 阶段)
- 未实现重试/退避(未来 `tavern doctor` 或独立 middleware)
- 未实现 Azure OpenAI 特定路径(用户可 gateway 转发 → Custom)
- 未做真实网络端到端测试(需要 key + 额度)

### 里程碑对齐

- **M0(骨架跑通)**:60% → **80%**(6 家 provider 全部就位,Extractor 之外的地基完成)
- **M1(状态与记忆)**:40%(未变)
- 剩余 M0 项:Extractor 双调用 + 死亡分支

---

## [0.5.0] · 2026-08-11 · SQLite 存档 + 场景日志 + REPL 命令

**主题**:玩家的进度不再归零。`/save` `/load` `/rewind` 兑现,`tavern play` 的每一回合都被持久化。M1 第一块拼图落地。

### 新增

- **`tavern.save` 子系统** `src/tavern/save/`
  - `schema.py` —— DDL + `SCHEMA_VERSION = 1`
  - `store.py` —— `Save` 类 + 模块级 `list_saves` / `delete_save`
  - `__init__.py` —— re-export 公共 API
- **SQLite 表结构(v1)**
  - `save_meta` —— schema_version、world_id、save_name、created_at、tavern_version(单行)
  - `world_state` —— turn_count、current_scene、day、time_of_day、updated_at(单行)
  - `scene_log` —— append-only 每 turn 一条,role ∈ {player, gm, system}
  - 索引 `idx_scene_log_turn`
  - 连接参数:`isolation_level=None` + `WAL` + `foreign_keys=ON`
- **公开 Python API**
  ```python
  from tavern.save import (
      Save, SaveState, Turn, SaveSummary,
      SaveError, SaveNameError, SaveNotFoundError,
      SaveExistsError, SchemaMismatchError,
      list_saves, delete_save, save_path, saves_dir,
      SCHEMA_VERSION,
  )
  ```
  - `Save.new(name, world_id)` / `Save.open(name)`
  - `save.append_turn(role, text, *, turn_no)`
  - `save.turns()` / `save.recent_turns(n)`
  - `save.rewind(pairs)`
  - `save.update_state(**fields)`
  - `save.copy_to(new_name)` —— 用 SQLite `Connection.backup()` 原子拷贝
  - 上下文管理器 `with Save.new(...) as s:` 支持
  - `close()` 幂等
- **`tavern play` 集成存档**
  - 默认存档 `default-<world_id>` 自动打开/新建
  - `--save <name>` 使用指定存档
  - `--new` 重置默认存档(先删后建)
  - 首屏 header 显示 `save: <name> · <n> turns`
  - `turn_count == 0` 时打印 `opening_hook` 并写入 system turn
  - `turn_count > 0` 时打印"continuing from turn N"+ 最近 6 turn 摘要
  - 每回合写 player + gm 两条 turn(共享同一 turn_no)
- **REPL 内新指令**
  - `/save [name]` —— 无 name 时确认已存;有 name 时 `copy_to` 并切换到新存档
  - `/load <name>` —— 关闭当前 + 打开另一个存档,找不到不 crash 只 error msg
  - `/saves` —— REPL 内表格显示
  - `/rewind [N]` —— 撤销最近 N 回合(默认 1)。空存档时 error 不 crash
  - `/help` —— 打印所有可用指令
  - 未知 `/xxx` —— `[unknown command] type /help`
- **`tavern saves` 顶层命令**
  - 表格:NAME / WORLD / TURNS / UPDATED
  - `--long` 加 path 列
  - 空态:`No saves yet. Run \`tavern play <world-id>\` to start one.`
- **存档名校验** —— `^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$`
  - 拒绝 `/` `\` `.开头` `-开头` `>64 字符` `非 ASCII`
- **Schema 版本校验** —— `Save.open` 打开时对比 `schema_version`,不一致抛 `SchemaMismatchError` 提示升级
- **文档**
  - `docs/PRD-save-scene-log.md` —— 本次功能的 PRD

### 变更

- `tavern --version` → `tavern 0.5.0`
- `tavern play` 首屏 header 现在包含 save 名与 turn 数
- REPL 提示从"type /quit to exit"变为"type /help for commands, /quit to exit"

### 测试

- 新增 40 个测试(140 → 180):
  - `tests/save/test_names.py`(4)—— 存档名校验边界
  - `tests/save/test_store.py`(23)—— 生命周期、turn 读写、rewind、copy、schema mismatch、list、delete
  - `tests/cli/test_play_save_integration.py`(13)—— play 跨会话持久化、`--new`、所有 slash 指令、`tavern saves`
- 覆盖率:save/store 97%,schema/init 100%(超过 90% 目标)
- 全 180 测试 5.4 秒跑完

### 设计取舍

- **每 turn 一条 vs 一回合合并** —— 每 turn 一条(DESIGN.md §六 数据模型草图如此)。让 rewind 直接跑 SQL WHERE、export novel 直接吃 role 字段
- **每次 write 一个事务** —— SQLite 单文件本就快,不批量;失败故事清晰
- **WAL journal_mode** —— 崩溃安全性 > 磁盘上多一个 `-wal` `-shm` 文件
- **copy_to 用 `Connection.backup()`** —— SQLite 内置原子拷贝,即使源在写也安全
- **存档名严格校验** —— path traversal 防护,拒绝非 ASCII(留待未来 slug 化)
- **schema 检测但不迁移** —— 首版只检测不匹配;迁移执行代码留到实际有 v2 时再做,避免过度设计
- **`/load` `/save NAME` 交换 conn 而非重新构造 Save** —— 直接改 save._path / save._conn 避免要在 REPL 循环里传引用回主循环(取舍是稍显 hacky,注释解释)
- **删除存档时同步清理 `-wal` `-shm`** —— 否则重开同名存档时 SQLite 会看到残留 WAL 产生 confusion

### 已知限制 & 后续

- Extractor / state_delta / HP / 死亡分支 —— 归入下一轮
- `/who` `/where` `/inv` `/status` —— 依赖 state_delta 有内容,归入下一轮
- `/export novel` —— 需要 LLM 组稿,可以在有 provider 之后做
- 场景摘要(Memory Keeper)—— schema v2 会加 `scene_summary` 表
- 存档间共享 world 目录:目前 world_id 单向引用,如果卸载世界包老存档仍能开(只读)但 play 会拒绝
- 无自动备份 / 版本历史;线性存档,与 DESIGN.md 决策 F 一致
- 无加密

### 里程碑对齐

- **M0(骨架跑通)** —— 保持 60%(本轮属 M1 前置,不推进 M0)
- **M1(状态与记忆)** —— **40%**(SQLite 存档 + 场景日志 + 5 个基础指令落地)。剩余:场景摘要 / NPC 好感度 / `/status` `/who` 等观察指令

---

## [0.4.0] · 2026-08-11 · LLM Provider 抽象层 + `tavern play`

**主题**:玩家的第一个可视界面 —— `tavern play <world-id>` 敲下去,故事就开始了。

### 新增

- **LLM Provider 抽象** `src/tavern/llm/`
  - `LLMProvider` Protocol(`typing.Protocol` + `@runtime_checkable`),三方法:`complete()` / `stream()` / `describe()`
  - `LLMError` 层级:`LLMAuthError` / `LLMNetworkError` / `LLMResponseError`
  - `default_stream()` 辅助:让新 provider 复用 `complete()` 就能满足 stream 协议
- **`EchoProvider`** —— 不发网络的演示后端
  - 回显最后一句用户输入,前缀 `[echo]`
  - `describe()` 明说 "offline demo"
  - 让 `tavern play` 在 CI / 无网络环境跑得动
- **`AnthropicProvider`** —— Claude Messages API
  - 用 stdlib `urllib.request` 发 POST(零第三方依赖)
  - `_build_request()` 是纯函数,可注入 `transport` 完整单元测试
  - `api_key` 缺失时构造函数就抛 `LLMAuthError`(fail fast)
  - `ANTHROPIC_API_KEY` 环境变量兜底
- **Provider 注册与工厂**
  - `PROVIDER_CLASSES`:`{"echo": "tavern.llm.echo:EchoProvider", "anthropic": ...}` 字符串路径,避免顶层导入所有 provider
  - `load_provider(role="default", cfg=None)`:role fallback 到 default,未知 provider 抛友好错误
- **`tavern play <world-id>` 命令**
  - 找已装世界 + 加载 pack + 实例化 provider + 打印 opening_hook + REPL
  - `/quit` `/exit` 或 Ctrl+D 或 Ctrl+C 干净退出
  - 提示行显示 `provider.describe()` —— 玩家知道自己在用什么后端
  - `--provider <role>` 切换 role(默认 "default")
  - 错误路径全部退出码 1 + 友好指令(缺 world / config / provider)
- **`echo` 加入 `tavern.llmconfig.PROVIDERS`** —— `tavern config init` 现在有 6 个选项

### 变更

- `tavern --version` → `tavern 0.4.0`
- CLI 帮助包含 `play` 子命令

### 测试

- 新增 31 个测试(109 → 140):
  - `tests/llm/test_echo.py`(6)—— Protocol 契约、空/多行、stream 一致性
  - `tests/llm/test_anthropic.py`(9)—— 构造、env 兜底、`_build_request` 结构、注入 transport 端到端、text 提取、错误分支
  - `tests/llm/test_registry.py`(6)—— load_provider 分派、role fallback、错误
  - `tests/cli/test_play_command.py`(10)—— tavern play e2e(用 Echo,不联网)
- 覆盖率:base/echo 100%,registry 96%,anthropic 74%(未覆盖部分是真 urllib 网络分支,PRD 明确排除)
- 全 140 测试 3 秒内跑完

### 设计取舍

- **Protocol 而非 abc.ABC** —— 松散契约,duck typing 友好,测试 fake 无需继承
- **动态导入 provider** —— 未来 100 个 provider 不拖累 CLI 启动
- **provider 层再做一次 env 兜底** —— 与 loader 层重复,是**故意的冗余**,防绕过 loader 的直接调用
- **EchoProvider 前缀 `[echo]`** —— 让玩家一眼看出不是真 GM
- **不发真网络测试** —— API key + 额度成本高,归入未来 `tavern doctor` 单独交付
- **无 `httpx`/`requests`** —— 保持零第三方依赖(v0.1.0 起的贯穿约束)
- **play 命令无状态** —— 存档是 M1,orchestrator 是 M0.2;这一步只做输入 → provider → 输出

### 已知限制 & 后续

- 只接了 Echo + Anthropic 两家 provider —— OpenAI/DeepSeek/Ollama/Custom 归入下一轮
- Narrator prompt 只组装 `tone + rules.summary`,不做完整上下文注入(NPC 卡、时间轴、Director note)
- 无 Extractor 调用 —— 无 state_delta 提取,世界状态不推进
- 无场景日志、无存档、无向量记忆 —— 都属于 M1+
- 无 `/save` `/who` `/inv` 等系统指令 —— play 现在只支持 `/quit` `/exit`
- 无打字机效果 / 流式输出可视 —— 内部有 stream,CLI 层还是同步 print

### 里程碑对齐

**M0(骨架跑通)进度更新** —— 60%(骨架 + 世界包加载 + 安装 + LLM 配置 + Provider 抽象 + play REPL)。剩余:Extractor 双调用、死亡分支、更多 provider。

---

## [0.3.0] · 2026-08-11 · LLM 配置管理

**主题**:`tavern config init / show / check / path` —— M0 里程碑最后一块拼图,LLM Provider 层的硬前置。

### 新增

- **`tavern config init [--force] [--provider PROV]`** —— 交互向导
  - 提示 provider(5 个内置:anthropic / openai / deepseek / ollama / custom)
  - 提示 model(每个 provider 有合理默认值,回车接受)
  - 提示 api_key(ollama 例外);允许留空由环境变量兜底
  - custom / ollama 额外提示 `base_url`
  - `--force` 覆盖已有 config
  - `--provider` 跳过 provider 提示但仍提示后续字段
  - 非 TTY 环境拒绝执行(引导用户改用手工编辑)
  - Ctrl+C / Ctrl+D 干净退出,不留半个文件(原子写:`.tmp` + `os.replace`)
- **`tavern config show [--reveal]`** —— 打印当前配置
  - 默认**遮蔽密钥**(`sk-a...f456` 格式)
  - 密钥字段识别:名字包含 `key/secret/token/password/apikey`(大小写不敏感)
  - `--reveal` 明文,顶部加红字警告
- **`tavern config check`** —— 校验 config.toml
  - C001 TOML 语法错(报行号)
  - C002 缺 `[llm.default]`
  - C003 provider 不在合法枚举
  - C004 model 缺失(warning)
  - C005 custom provider 缺 base_url
  - Cw01 key 空且 env 也无(warning)
  - Cw02 `[ui]` 字段值不合理
  - Cw03 未识别的 section / role
  - Ci01 key 来自环境变量(info)
- **`tavern config path`** —— 打印 config.toml 绝对路径(单行,方便脚本 `$(tavern config path)`)
- **环境变量兜底** —— `api_key` 空时按 provider 自动读:
  - `anthropic` → `ANTHROPIC_API_KEY`
  - `openai` → `OPENAI_API_KEY`
  - `deepseek` → `DEEPSEEK_API_KEY`
  - 读到时设 `api_key_from_env=True` **不写回文件**(避免密钥泄漏)
- **公开 Python API**
  ```python
  from tavern.llmconfig import (
      Config, LLMRoleConfig, UIConfig, PROVIDERS,
      load_config, load_config_raw, check_config,
      init_interactive, write_config,
      mask_secret, is_secret_field,
  )
  ```
- **模块结构**
  - `src/tavern/llmconfig/schema.py` —— Config dataclass + PROVIDERS 常量 + mask 辅助
  - `src/tavern/llmconfig/loader.py` —— 读盘 + 环境变量合并
  - `src/tavern/llmconfig/writer.py` —— 交互向导 + 原子写 TOML
  - `src/tavern/llmconfig/check.py` —— 校验规则

### 变更

- `tavern --version` 现在打印 `tavern 0.3.0`
- CLI 帮助包含 `config` 子命令组

### 测试

- 新增 42 个测试(67 → 109):
  - `tests/llmconfig/test_schema.py`(5)—— mask + secret-field 识别
  - `tests/llmconfig/test_loader.py`(7)—— 文件缺失、env 兜底、TOML 语法
  - `tests/llmconfig/test_check.py`(10)—— 每条规则的正负样本
  - `tests/llmconfig/test_writer.py`(9)—— 交互向导 + TOML 序列化
  - `tests/cli/test_config_command.py`(11)—— CLI 端到端 4 个子命令
- 覆盖率:loader/schema 100%,writer 93%,check 90%,均 ≥ 85% 目标
- 全部 109 测试 2 秒跑完

### 设计取舍

- **交互式 vs `config set` 声明式接口** —— 交互式。USAGE.md 承诺是"3 问 3 答";用户想改字段直接编辑 TOML 更直接
- **密钥默认遮蔽** —— screenshot/paste-to-issue 是常见场景,default safe
- **不写回环境变量解析结果** —— `api_key = ""` 加 env 兜底时,resolved 值只在内存,永不落盘
- **拒绝非 TTY init** —— 自动化场景应直接生成 TOML,不该假装键盘输入
- **手写 TOML dumper** —— 保持零第三方依赖(vs 引入 `tomli-w`)
- **`src/tavern/llmconfig/` 而非 `config/`** —— `tavern.config` 已用于文件系统布局(v0.2.0),避免冲突

### 已知限制 & 后续

- 不验证 API key 有效性(需要网络请求;归入未来 `tavern doctor`)
- 不管理多套 profile(dev/prod 切换)—— 用 `TAVERN_CONFIG_HOME` 达到等效
- 不加密密钥 —— CLI 惯例;未来可接系统 keychain(`keyring` 库)
- 无 `tavern config set/get` —— 当前设计中不需要

### 里程碑对齐

**M0(骨架跑通)进度更新** —— 40%(项目骨架 + 世界包加载 + 世界包安装 + LLM 配置)。剩余:LLM Provider 抽象层、orchestrator 回合循环、Narrator/Extractor prompt、死亡分支。

---

## [0.2.0] · 2026-08-11 · 世界包安装管理

**主题**:`tavern install / list / uninstall` —— 世界包分发链路闭环。

### 新增

- **`tavern install <path>`** —— 从单文件 / 目录 / `.tar.gz` / `.tgz` / `.zip` 装世界包
  - 装完自动放到 `<TAVERN_CONFIG_HOME>/worlds/<world-id>/`
  - 装前调用 validator;有 error → 拒装(`--force` 绕过)
  - 同 id 已装 → 拒装(`--force` 覆盖,会保留旧目录中的用户改动的清理策略见下)
  - `--no-validate` 跳过校验
- **`tavern list [--long]`** —— 列出已装世界
  - 短格式:ID / NAME / VERSION / TOKENS 表格,CJK 字符按显示宽度对齐
  - `--long`:附加 path / installed / source / source_type
  - 空态提示:`No worlds installed. Use \`tavern install <path>\` to install one.`
- **`tavern uninstall <world-id> [--yes]`** —— 移除已装世界
  - 默认交互确认 `[y/N]`;`--yes` 跳过
  - 找不到 → 退出 1 并说明
- **`~/.config/tavern/` 目录布局**
  - 默认路径 `~/.config/tavern/worlds/`
  - `$TAVERN_CONFIG_HOME` 覆盖(测试与容器场景)
  - `$XDG_CONFIG_HOME` 兜底(遵循 XDG Base Directory)
- **`.tavern-installed.toml`** 元数据 —— 每个已装世界包内嵌
  - `installed_at`(UTC ISO 8601)
  - `source`(绝对路径)
  - `source_type`(file / dir / tar.gz / zip)
  - `tavern_ver`(装它的引擎版本)
- **归档解压安全**
  - 拒绝 zip slip(`../` 路径)
  - 拒绝绝对路径成员
  - 拒绝含符号/硬链接的 tar
  - Python 3.12+ 使用 `tarfile.extractall(filter="data")` 内置沙箱
- **归档形态自动识别**
  - `tar czf world.tar.gz my-world/` 解压出的 `staging/my-world/` 会被自动进入
  - 单文件源规范化为 `<world-id>/world.toml` 目录结构
- **公开 Python API**
  ```python
  from tavern import install, list_installed, uninstall, InstallError, InstalledWorld
  ```
- **文档**
  - `docs/PRD-worldpack-install.md` —— 本次功能的 PRD

### 变更

- `tavern --version` 现在打印 `tavern 0.2.0`
- CLI 帮助包含 `install / list / uninstall` 三个新子命令

### 测试

- 新增 32 个测试(35 → 67):
  - `tests/test_config.py`(4 个)—— 环境变量优先级
  - `tests/worldpack/test_install.py`(18 个)—— install/list/uninstall 逻辑,zip slip,--force,元数据
  - `tests/cli/test_install_command.py`(10 个)—— CLI 端到端
- 全部使用 `tavern_home` fixture 隔离,不污染真实 `~/.config/tavern/`
- 覆盖率:install 模块 85%,validator 97%,schema/tokens/config 100%,总 71%(CLI 通过子进程测,不计入 unit coverage)
- 1.33 秒跑完

### 设计取舍

- **规范化为目录**:即使源是单文件 `world.toml`,也建 `<world-id>/world.toml`。理由:后续加 npcs/ locations/ 布局一致,list/uninstall 逻辑统一
- **`--force` 覆盖时先 `rm -rf`**:不做增量 merge。理由:世界包应被视为不可变实体,合并语义反直觉
- **元数据不放在 `.tavern/` 子目录**:直接 `.tavern-installed.toml` 顶层。理由:一个文件比一个目录轻,且世界作者若手动清理也一眼可辨
- **归档中的顶层单目录自动进入**:处理 `tar czf my-world.tar.gz my-world/` 常见场景。多目录时留给用户手动打包

### 已知限制 & 后续

- 不支持 URL 直装(`tavern install https://...`)—— P4/P5
- 不支持世界包间依赖 —— 暂无场景
- 不支持版本回滚 —— 用户自行备份
- `tavern update <id>`(读元数据里的 source 再 --force install)—— 可作为 P2 的顺手扩展

---

## [0.1.0] · 2026-08-11 · 首个可运行组件

**主题**:Worldpack 加载与校验(`tavern validate`)。

### 新增

- **Python 项目骨架** —— `pyproject.toml`(hatchling build,uv/pipx 分发就绪),`src/tavern/` 命名空间
- **`tavern` CLI 入口** —— `pyproject.toml` 声明的 script,`python -m tavern` 也可用
- **`tavern validate <path>` 子命令**
  - 支持单文件 `world.toml` 或世界包目录
  - 分级诊断:error / warning / info
  - `--strict`(warning 视为失败,用于 CI)
  - `--verbose`(打印 info 级诊断)
  - `NO_COLOR=1` 环境变量关闭 ANSI 色
  - 退出码规范:0 通过 / 1 校验失败 / 2 CLI 使用错误
- **Worldpack 模块** `src/tavern/worldpack/`
  - `schema.py` —— dataclass 定义 `WorldPack / World / NPC / Location / Template`
  - `loader.py` —— 递归解析 world.toml + `npcs/` + `locations/` + `templates/` + `intro.md`
  - `validator.py` —— 15+ 条独立校验规则
  - `diagnostics.py` —— `Diagnostic` / `ValidationReport` + 人读渲染
  - `tokens.py` —— 中英文启发式 token 估算(零依赖)
- **公开 Python API** —— `from tavern import load_worldpack, validate_worldpack`
- **示例世界包**
  - `examples/minimal-tavern/` —— 30 行最小可运行世界(M0 里程碑要用)
  - `examples/example-jianghu/` —— 完整世界包,含 NPC / template / intro.md
- **测试套件** `tests/`
  - 35 个测试,涵盖:loader / validator / tokens / CLI 端到端
  - Fixture 覆盖 happy path + 7 种错误场景
  - 总覆盖率 77%,核心 validator 97%,schema/tokens 100%
  - `.venv/bin/pytest` 0.45 秒跑完
- **文档**
  - `docs/PRD-worldpack-validate.md` —— 本次功能的产品需求
  - `docs/gap-analysis-2026-08-11.md` —— 项目功能缺口分析
  - `docs/CHANGELOG.md` —— 本文件

### 校验规则清单

**Error(阻断)**:
- `E001` 路径不存在
- `E002` 目录缺 `world.toml`
- `E003` TOML 语法错(报行号)
- `E004` 缺必填字段(id/name/setting/initial_tavern)
- `E005` `world.id` 不是合法 slug
- `E006` `world.version` 不是合法 SemVer
- `E007` `present_npcs` 引用不存在的 NPC
- `E008` NPC 文件名与 id 不一致
- `E009` NPC id 重复
- `E010` 模板 `pc.hp.current > pc.hp.max`

**Warning(建议,`--strict` 才阻断)**:
- `W001` 缺 intro/description
- `W002` 无 factions
- `W003` 无 timeline
- `W004` 单字段 > 2000 字符
- `W005` 世界包估算 token > 8000
- `W006` 无 templates
- `W007` `honeymoon_turns > 200`
- `W008` `opening_hook` 太短(< 50 字符)
- `W009` NPC 缺 goals 或 secrets

**Info(verbose 才显示)**:
- `I001` 统计:世界名/版本 + NPC/faction/timeline/template 计数 + 估算 tokens

### 设计取舍

- **零第三方运行时依赖** —— stdlib `tomllib`(3.11+)+ dataclasses 足够;分发时装出即用
- **不引 pydantic** —— 手写校验规则更能给出人读诊断
- **Token 估算是启发式的** —— 只用于 warning,不做精确计费;未来接入 tokenizer 属于非破坏性改动

### 后续里程碑联动

- **M0 骨架跑通** —— orchestrator 可直接 `load_worldpack("examples/minimal-tavern/")`
- **M4 世界包生态** —— `tavern install/search` 复用 loader + validator,拒绝装校验不过的包
- **CI** —— `.github/workflows/*.yml` 里跑 `tavern validate --strict examples/*/`

### 里程碑对齐

| 里程碑 | 本次占进度 |
|---|---|
| M0(骨架跑通) | 20%(项目骨架 + 世界包加载) |
| M4(世界包生态) | 30%(schema + validator 已就位) |

### 快速验证

```bash
# 用 uv 装依赖(仅 dev 用 pytest)
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python pytest pytest-cov

# 跑测试
.venv/bin/pytest -q

# 校验示例世界
PYTHONPATH=src .venv/bin/python -m tavern validate examples/minimal-tavern/world.toml
PYTHONPATH=src .venv/bin/python -m tavern validate examples/example-jianghu/
```

### 已知限制

- 目前 `tavern install` / `list` / `search` 未实现 —— 世界包需要手动放置或直接传路径
- 无 `--json` 输出,人读格式先行
- 尚未打包发布到 PyPI

### 贡献者

- Tavern Team(初版)
