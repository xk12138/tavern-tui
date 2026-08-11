# PRD · `/export novel` 小说导出

- 状态:草案 → 已实现
- 版本:v1.0
- 日期:2026-08-11
- 依赖:v0.5.0 场景日志 · v0.6.0 全 6 家 provider
- 里程碑:DESIGN 决策 J & M3 里程碑的 "导出" 部分

---

## 一、问题陈述

DESIGN.md §四关键节点写死了"原始 turn 日志无论走到哪都要保留 —— 小说导出功能依赖它",§十决策 J 拍板"支持 `/export novel`,保留完整 turn 日志作为素材",§九 M3 里程碑列出 "`/export novel` —— 把 turn 日志重写为第三人称小说"。USAGE.md §六第一批系统指令、§十默认输出路径、§十一疑难解答都对玩家做出承诺:

```
/export novel [path]     把当前进度重写为第三人称小说文本
```

**现状**:所有前置就位 —— v0.5 存了完整 turn 日志(role/text/turn_no),v0.6 有 6 家 provider,`LLM_ROLES` 里 export 早在 v0.3 就注册。**只差一个模块把它们串起来**。

### 影响

| 用户 | 痛点 |
|---|---|
| **玩家** | 玩了 50 回合的故事只能自己在终端翻;没有"作品输出"的方式;体验断在最后一步 |
| **世界作者** | 想收集精彩玩法示例分享给别的玩家,得手动 copy-paste |
| **社区** | 缺少可分享内容 —— 没人分享 = 没人被吸引来 |

### 为什么这轮做

- **所有前置都在**;这一轮的工作是**编排**,不是造轮子
- **范围紧凑**:一个 module + 一个 CLI + 一个 REPL 指令
- **可完全测试**:EchoProvider + fake transport 走完整个链路
- **玩家立刻有价值**:"我玩到这里,导出一份"

---

## 二、目标与非目标

### 2.1 必须

1. **`ExportEngine`**:读取存档 → 组装 prompt → 调 LLM → 拿到 md → 落盘
2. **顶层命令 `tavern export novel <save_name> [--output PATH] [--provider ROLE]`**
3. **REPL 内 `/export novel [PATH]`**:在 `tavern play` 会话里可用
4. **默认输出路径**:`~/tavern-novels/<save_name>-<YYYYMMDD-HHMMSS>.md`(USAGE §十)
5. **专用 provider role**:优先用 `export` role,不存在则 fallback 到 `default`(USAGE §十一疑难解答:"可以为 export 单独指便宜模型")
6. **Front matter**:文件开头 YAML front matter 记录 world / save / turn_count / provider / generated_at
7. **分块策略**:内容超阈值时自动分段调 LLM,最后拼接
8. **过滤 system turn**:opening_hook 之类的 system 消息不作为素材,或作为独立引言段
9. **不覆盖同名文件**:若目标存在 → 拒绝(除非 `--force`)
10. **完整测试**:单元测试 export engine,e2e 测 CLI + REPL

### 2.2 非目标

- 不做**多风格切换**(第一人称/第三人称/散文/剧本 …)—— 首版就"第三人称叙事小说",后续可加 `--style`
- 不做**多语言输出**(自动继承世界包 tone 的语言)
- 不做**图片/封面**
- 不做**分章节**(全篇一段;未来 `--chapters` 可加)
- 不做**同步预览**(纯 batch;写完打路径)
- 不做**跨存档合并**(单存档单文件)
- 不修改存档任何内容(只读)

---

## 三、用户故事

### US-1:玩到第 50 回合想输出
> "作为玩家,`/export novel` 应该 30 秒内(Echo 更快)生成一份 md,路径打印出来我能立刻打开。"

**验收**:
- REPL 内 `/export novel` 无参 → 默认路径写盘
- 打印 `Novel exported to <path>`
- REPL 继续,不退出

### US-2:指定路径
> "`/export novel ~/desktop/my-story.md` 应该直接写那里。"

**验收**:
- 目标目录不存在时自动创建
- 目标文件已存在 → error(不覆盖),提示 `--force`

### US-3:导出便宜跑
> "小说导出费 token,我想用 DeepSeek 便宜模型跑,不用 default 的 Claude。"

**验收**:
- config.toml 里配 `[llm.export]` → 走 export role
- 不配 → fallback 到 default

### US-4:脚本化
> "`tavern export novel my-run --output ./out.md`,退出码 0 后我脚本继续。"

**验收**:
- 顶层命令能不启 REPL 就导出
- 找不到存档 → 1
- 输出目标不可写 → 1
- provider 报错 → 1

### US-5:导出后依然可继续玩
> "导出应该是只读,存档不变,继续玩不受影响。"

**验收**:
- 导出前后 `save.state.turn_count` 不变
- turns 数不变
- 导出期间可正常 append_turn

---

## 四、功能规格

### 4.1 CLI 接口

```
tavern export novel <SAVE_NAME> [--output PATH] [--provider ROLE] [--force]

  SAVE_NAME       存档 id(见 `tavern saves`)
  --output PATH   输出 md 路径。默认 ~/tavern-novels/<save>-<timestamp>.md
  --provider ROLE 用哪个 role(默认: export, 不存在则 default)
  --force         覆盖已存在的输出文件

Exit codes:
  0   success
  1   save not found / world unavailable / provider error / target exists
  2   CLI misuse
```

REPL 内:

```
/export novel [PATH]

  与顶层等价,但只支持 PATH 参数(不支持 --provider,当次会话已锁定 provider)
```

### 4.2 输出格式

```markdown
---
title: <世界名> · <存档名>
world: <world-id>
save: <save-name>
turns: <N>
provider: <provider.describe()>
generated_at: 2026-08-11T15:47:03Z
tavern_version: 0.7.0
---

# <世界名>

<可选:世界包 intro.md 或 world.description 的前两段作为"世界背景">

---

<LLM 生成的小说正文>

---

*本篇由 Tavern 于 <日期> 从存档 `<save-name>` 生成。turn 数:<N>。*
```

### 4.3 分块策略

**阈值**:5000 characters 输入(近似 3000 tokens)—— 保守,避免 truncation。

单块能塞下就一次调 LLM;超过就:
1. 按 turn 对(player+gm)分组,连续累积直到接近阈值
2. 每块调一次 LLM,产出小说片段
3. 每块之后的 continuation prompt 包含"接续前一段"提示,提供前一段结尾 300 字作为上下文
4. 最后拼接为完整正文

**注**:分块会导致风格微妙不一致 —— 可接受,是"能导出"vs"能不能导出"的差别。未来可加 `--single-shot` 强制一次调用。

### 4.4 Prompt 模板

**单块 / 首块**:

```
You are a novelist adapting an interactive story into prose fiction.

World: {world_name}
Setting: {world_setting_tone}

Below is a transcript of an interactive session between a player and a GM.
Rewrite it as a coherent third-person past-tense narrative.

Rules:
- Third-person past tense.
- Preserve every meaningful action, dialogue, and outcome.
- Do NOT invent new plot points that aren't in the transcript.
- Do NOT add meta-commentary or breaking-the-fourth-wall.
- Use the world's tone (see above). If tone is empty, default to neutral prose.
- Output only the story text — no headings, no "Chapter", no notes.

Transcript:
{transcript_block}

Now write the narrative for this section.
```

**续块**:开头附加

```
This is a continuation. Here is the last paragraph you wrote:

{previous_tail}

Continue seamlessly. Do NOT repeat what came before.
```

### 4.5 Transcript 格式化

对每个 turn 对:
```
Player: {player_text}
GM: {gm_text}

```

**system turn 处理**:opening_hook 作为 transcript 前置的"Opening scene:" 段落,而不是当成 player/gm 消息。

### 4.6 数据流

```
Save.open(name)
     ↓
turns = save.turns()  (含 system + player + gm)
     ↓
opening = 第一条 system turn 的文本(若存在)
pairs   = [(p, g), (p, g), ...]  从 turns 里配对
     ↓
build_chunks(pairs, threshold=5000)
     ↓
for i, chunk in enumerate(chunks):
    system_prompt = _build_novel_prompt(world, opening, ...)
    user_prompt   = format_transcript(chunk)  + (previous_tail if i>0)
    text         = provider.complete(user_prompt, system=system_prompt)
    output.append(text)
     ↓
write front matter + intro + '\n'.join(output) + footer
     ↓
落盘
```

### 4.7 依赖

**stdlib only**,`datetime` + `pathlib`。

### 4.8 目录约定

`~/tavern-novels/`(USAGE §十)—— 通过 `Path.home()` 拿。**不放 tavern_home 下**,理由:小说是"给外面看的内容",与 tavern 内部数据分开;用户导出后经常拖到 iCloud/Dropbox。

**测试隔离**:引入 `TAVERN_NOVELS_HOME` 环境变量覆盖,允许测试用 tmp_path。类似 `TAVERN_CONFIG_HOME`。

### 4.9 错误路径

| 情况 | 行为 |
|---|---|
| SAVE_NAME 不存在 | exit 1 + "no such save; run \`tavern saves\`" |
| 存档为空(turn_count = 0) | exit 1 + "save has no turns to export" |
| 目标文件已存在且无 --force | exit 1 + "output exists; use --force" |
| 目标目录不可写 | exit 1 + OSError 消息 |
| provider 抛 LLMError | exit 1 + provider 错误消息 |
| REPL 内 /export 错误 | 打印到 stdout,不终止 REPL |

---

## 五、实现设计

### 5.1 模块结构

```
src/tavern/
├── export/
│   ├── __init__.py         ← re-export 公共 API
│   ├── novel.py            ← ExportEngine, format_transcript, build_chunks
│   └── paths.py            ← novels_home() + default_output_path()
└── cli.py                  (+ export subcommand + /export slash)
```

### 5.2 关键 API

```python
# src/tavern/export/novel.py

@dataclass
class ExportResult:
    output_path: Path
    turn_count: int
    chunk_count: int

class ExportError(Exception): ...

def export_novel(
    save: Save,
    world_pack: WorldPack | None,        # for name / tone / intro
    provider: LLMProvider,
    *,
    output: Path | None = None,          # default computed by paths.default_output_path
    force: bool = False,
    threshold_chars: int = 5000,
) -> ExportResult:
    """Return ExportResult after writing the novel to disk."""

# src/tavern/export/paths.py

def novels_home() -> Path:
    """~/tavern-novels or $TAVERN_NOVELS_HOME."""

def default_output_path(save_name: str) -> Path:
    """<novels_home>/<save_name>-<YYYYMMDD-HHMMSS>.md"""
```

### 5.3 分块辅助

```python
def _pair_turns(turns: list[Turn]) -> tuple[str | None, list[tuple[Turn, Turn]]]:
    """Return (opening_text, [(player, gm), ...]).

    - The first `system` turn (if any) becomes `opening_text`.
    - Every player turn is paired with the immediately-following gm turn.
    - Orphan turns (player without gm, or vice versa) are silently skipped —
      shouldn't happen if the REPL wrote them, but we don't blow up.
    """

def _build_chunks(pairs: list[tuple[Turn, Turn]], threshold_chars: int) -> list[list[tuple[Turn, Turn]]]:
    """Greedy accumulation until threshold; new chunk starts."""
```

### 5.4 CLI wiring

`tavern export novel` 顶层:
- resolve save + provider(优先 role="export", 不在则 "default")
- 拿 world → 通过 `list_installed()` + `load_worldpack(world_id)`
- 调 `export_novel`
- 打印 `Novel exported to <path>`

`/export novel [PATH]` REPL 内:
- 复用同一 `export_novel` 函数
- provider 用当前 REPL 的 provider(不会切 role,一致性优先)

### 5.5 world_pack 缺失时的降级

如果 save 里的 world_id 对应的世界包已卸载:
- 不阻止导出(用户可能只想拿故事)
- Front matter 里 world 字段仍写(从 save.world_id)
- prompt 里 world_name/tone 用 fallback:"Unknown world" / 空 tone
- 打印 warning 到 stderr

### 5.6 分块的 tail 提取

`_last_paragraph(text, max_chars=300)`:
- 从末尾往前找双换行,截取最后一段
- 长度截 max_chars
- 用于续块 prompt 的"承接上文"

### 5.7 输出编排

```python
def _render_output(
    result_text: str,
    save: Save,
    pack: WorldPack | None,
    provider: LLMProvider,
    intro_text: str | None,
) -> str:
    front = _render_frontmatter(save, pack, provider)
    parts = [front, "\n"]
    if pack:
        parts.append(f"# {pack.world.name}\n\n")
    if intro_text:
        parts.append(intro_text.strip() + "\n\n---\n\n")
    parts.append(result_text.strip() + "\n\n")
    parts.append(_render_footer(save))
    return "".join(parts)
```

---

## 六、测试策略

### 6.1 单元

`tests/export/test_paths.py`:
- default_output_path 包含 save name + timestamp
- $TAVERN_NOVELS_HOME 覆盖生效

`tests/export/test_novel.py`:
- `_pair_turns` 处理:仅 system / 单个 pair / 多个 pair / 孤立 turn
- `_build_chunks` 按阈值切
- `_last_paragraph` 提取
- `export_novel` 用 EchoProvider,验:
  - 输出文件存在
  - front matter 里有 world/save/turns
  - 空 turn_count 抛 ExportError
  - target exists 且 force=False 抛
  - target exists 且 force=True 覆盖
  - world_pack=None 也能跑
- 分块场景:小阈值(比如 500)触发多块

### 6.2 CLI e2e

`tests/cli/test_export_command.py`:
- `tavern export novel <name>` 走完 → 退出 0 + 打印路径 + 文件存在
- 存档不存在 → 1
- 目标已存在 → 1;`--force` → 0
- `--output` 指定路径生效
- 玩几轮后立刻导出:内容里 echo 的输入片段出现

`tests/cli/test_play_export_slash.py`:
- REPL 内 `/export novel` 后能继续 `/quit`
- `/export novel` 无 turn 时 → 打印错误但不 crash

### 6.3 隔离

- `TAVERN_CONFIG_HOME` fixture(已有)
- 新增 `novels_home` fixture 设置 `$TAVERN_NOVELS_HOME`

---

## 七、风险与取舍

| 议题 | 决定 |
|---|---|
| 单调用 vs 分块 | **默认分块** with 5000 chars 阈值。避免小型 provider truncation;单块也走同一路径(chunk_count=1)。未来可加 `--single-shot` |
| Front matter YAML 格式 | **是**。多数 markdown 阅读器兼容;机器可读;不影响正文渲染 |
| 是否让 LLM 生成小说标题 | **不**。首版用 `<世界名>` 作为 h1;LLM 生成标题风格不可控,徒增变量 |
| system turn 处理 | **首条作为"opening scene",其余丢弃**。opening_hook 是玩家看到的第一段,忽略它会让小说少个开场;其他 system 是引擎注入的调试信息,不该进小说 |
| ~/tavern-novels vs 存档目录 | **~/tavern-novels**(USAGE §十),独立于 tavern_home。小说是给外面看的,不该藏在 config 目录 |
| 输出编码 | UTF-8 无 BOM |
| 完成后返回 REPL 还是自动退出 | REPL 内 export 后**继续**,不退出。玩家可能想接着玩 |
| 支持自定义 style / 风格切换 | **首版不做**,预留 `--style` 参数位;可以在 PRD 追加时加 |
| 分块间失败重试 | **不做**。一次失败即整体失败;因为分块之间有 tail 依赖,重试需要严谨的状态管理,复杂度不值 |
| Provider 特定优化(比如 prompt caching) | **不做**。走通用 provider.complete 接口 |

---

## 八、验收指标

- `tavern export novel <save>` → 退出 0,打印路径,文件内容非空
- Front matter 完整(world/save/turns/provider/generated_at)
- 覆盖率:export/ ≥ 90%
- 测试仍 <8 秒(留 3 秒给分块 e2e)
- REPL `/export novel` 生效,导出后继续玩不受影响
- 空存档 → 友好错误

---

## 九、后续联动

- **`--style` 参数**:第一人称 / 剧本 / 散文 / 短篇 …
- **`--chapters N`**:自动分章
- **Novel index**:`tavern novels` 列出所有导出的 md 文件
- **World-aware prompt**:富世界(有 NPC / faction)时给 LLM 更多上下文,产出质量更高
- **Extractor 落地后**:小说输入里加入 state_delta 摘要(某场战斗的 HP 变化),让叙事更有张力
