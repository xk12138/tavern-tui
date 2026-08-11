# PRD · 世界包安装与管理(`tavern install / list / uninstall`)

- 状态:草案 → 已实现
- 版本:v1.0
- 日期:2026-08-11
- 依赖:v0.1.0 交付的 loader + validator

---

## 一、问题陈述

上一版发布了 `tavern validate`,世界作者能校验作品。**但作品验通过之后,没地方装。**

USAGE.md §四 已经向用户承诺:

```bash
tavern install ./my-world.toml
tavern install ~/Downloads/some-world/
```

WORLD_BUILDING.md §九.2 承诺 `tar czf my-world.tar.gz my-world/` 之后对方 `tavern install ./my-world/` 即可。

**现状**:上述命令都不存在。玩家拿到世界包后无路径可走;`~/.config/tavern/worlds/` 目录也从未被创建。

### 影响

| 用户 | 痛点 |
|---|---|
| **玩家** | 拿到 `.toml` 后不知放哪;想切换世界要手动 `cp -r` |
| **世界作者** | 分发链路断了 —— "写完 → 校验 → 装" 三步只走通两步 |
| **未来的 `tavern play`** | 需要"已安装世界列表"作为世界选择器数据源;没有 install 就没有列表 |

---

## 二、目标与非目标

### 2.1 必须

1. `tavern install <path>` —— 装单文件 world.toml / 世界包目录 / `.tar.gz` / `.zip` 归档
2. `tavern list` —— 列出已安装的世界(id、name、version、path)
3. `tavern uninstall <world-id>` —— 移除已安装世界(需二次确认或 `--yes`)
4. 环境变量 `TAVERN_CONFIG_HOME` 覆盖默认 `~/.config/tavern/`(测试与容器场景必需)
5. 安装前**先跑 `validate`**,存在 error 时拒绝(带 `--force` 绕过)
6. 同 id 世界已存在时:默认拒绝,`--force` 覆盖(打印被覆盖的版本号,便于回滚决策)
7. 输出 stable format(供机器读的 `--json` 留作 P2)

### 2.2 非目标

- 不做 `tavern search`(需社区索引,P5)
- 不做 URL 直装(`tavern install https://...`)——先本地闭环
- 不做世界包间依赖(暂无场景)
- 不做版本回滚 —— 用户自行备份

---

## 三、用户故事

### US-1:装单文件世界
> "我下载了 `xiaoshuo.toml`,`tavern install ./xiaoshuo.toml`,3 秒内装完并显示 'installed world <id> v<version>'。"

### US-2:装目录世界
> "我 clone 下来一个世界包 repo,`tavern install ./some-world/`。它自动把整个目录复制到 `~/.config/tavern/worlds/<id>/`。"

### US-3:装 tar.gz 归档
> "我拿到一份 `my-world.tar.gz`。`tavern install my-world.tar.gz`——解压 + 校验 + 安装,一步到位。"

### US-4:列出已装世界
> "`tavern list` 应该给出:世界 id、名字、版本、安装位置、上次修改时间。"

### US-5:卸载
> "`tavern uninstall my-jianghu`——问一句 `Are you sure? [y/N]`,y 才删。加 `--yes` 跳过确认。"

### US-6:冲突处理
> "同 id 装过了,`tavern install` 应报错并列出已有版本;`--force` 才覆盖。"

### US-7:校验失败拒装
> "装一个坏世界,应该拒绝并打印校验诊断;`--force` 才装(仅当理智地愿意接受风险)。"

---

## 四、功能规格

### 4.1 CLI 接口

```
tavern install <PATH> [--force] [--no-validate]

  PATH             .toml / 目录 / .tar.gz / .tgz / .zip
  --force          覆盖已存在的同 id 世界,且校验有 error 时也装
  --no-validate    跳过校验(不推荐)

tavern list [--long]

  --long           显示详细字段(路径、tokens、mtime)

tavern uninstall <WORLD_ID> [--yes]

  WORLD_ID         世界的 id (来自 world.toml [world].id)
  --yes,-y         跳过 [y/N] 确认

退出码:
  0    成功
  1    业务失败(校验不过 / 已存在 / 找不到)
  2    CLI 使用错误
```

### 4.2 目录布局

```
~/.config/tavern/                     ← 或 $TAVERN_CONFIG_HOME
├── config.toml                       ← 未来 LLM 配置(P2 会引入)
└── worlds/
    ├── my-jianghu/                   ← install 目录源
    │   ├── world.toml
    │   ├── npcs/...
    │   └── .tavern-installed.toml    ← 元数据:installed_at, source
    ├── my-cthulhu/                   ← install 单文件源(也被规范化为目录)
    │   ├── world.toml
    │   └── .tavern-installed.toml
    └── my-scifi/                     ← install 归档源(解压后)
        ├── world.toml
        └── .tavern-installed.toml
```

**关键决定**:所有 install 都规范化为目录 —— 即使源是单个 `.toml`,也建 `<world-id>/world.toml`。理由:未来加 npcs/ locations/ 时布局一致,list/uninstall 逻辑统一。

### 4.3 `.tavern-installed.toml` 元数据

```toml
[install]
installed_at = "2026-08-11T15:47:03Z"
source       = "/Users/alice/Downloads/my-jianghu.toml"
source_type  = "file"    # "file" | "dir" | "tar.gz" | "zip"
tavern_ver   = "0.1.0"
```

用途:
- `list --long` 显示来源
- 未来 `tavern update` 可以 re-install 同 source
- 调试用户 bug 时定位来源

### 4.4 安装流程

```
tavern install <path>
     ↓
1. resolve source_type (file / dir / tar.gz / zip)
     ↓
2. 展开到临时目录(dir 直接用;归档解压;单文件在临时目录建 dir + 复制)
     ↓
3. 找到 world.toml 位置(可能在解压出的顶层子目录里)
     ↓
4. 除非 --no-validate:调 validate_worldpack
     - 有 error → 除非 --force,退出 1
     - 有 warning → 打印,不阻断
     ↓
5. 读 world.id;目标 = TAVERN_HOME/worlds/<id>/
     - 已存在 → 除非 --force,退出 1
     - --force → 先 rm -rf 老目录
     ↓
6. rsync 语义拷贝(临时目录 → 目标目录)
     ↓
7. 写 .tavern-installed.toml
     ↓
8. 打印 "installed world <id> (<name>) v<version> → <path>"
```

**归档解压边界**:
- 用 stdlib `tarfile` / `zipfile`
- 只解压普通文件和目录;拒绝符号链接与绝对路径成员(zip slip 防护)
- 归档如果只有一个顶层目录(常见 `tar czf world.tar.gz my-world/` 结果),自动进入该目录找 `world.toml`

### 4.5 list 输出格式

```
$ tavern list

ID              NAME       VERSION   TOKENS
my-jianghu      江湖夜雨    0.2.1     ~1240
minimal-tavern  无名酒馆    0.1.0     ~140
```

```
$ tavern list --long

my-jianghu
  name       : 江湖夜雨
  version    : 0.2.1
  tokens     : ~1240
  path       : /Users/alice/.config/tavern/worlds/my-jianghu
  installed  : 2026-08-11T15:47:03Z
  source     : /Users/alice/Downloads/my-jianghu.toml
```

空列表时打印:
```
No worlds installed. Use `tavern install <path>` to install one.
```

### 4.6 uninstall 交互

```
$ tavern uninstall my-jianghu
About to remove world 'my-jianghu' (江湖夜雨 v0.2.1)
  path: /Users/alice/.config/tavern/worlds/my-jianghu
Continue? [y/N]: y
Removed world 'my-jianghu'.
```

`--yes` 跳过 prompt。

---

## 五、实现设计

### 5.1 模块结构

```
src/tavern/
├── cli.py                    ← 新增 install/list/uninstall 子命令
├── config.py                 ← 新增:TAVERN_CONFIG_HOME 解析 + 目录布局
└── worldpack/
    └── install.py            ← 新增:install/list/uninstall 业务逻辑
```

### 5.2 依赖

**仍然 stdlib only**:
- `tarfile` / `zipfile` —— 内置
- `shutil` —— 拷贝
- `pathlib` / `datetime` —— 显然

### 5.3 关键接口

```python
# src/tavern/config.py
def tavern_home() -> Path: ...              # 取 $TAVERN_CONFIG_HOME 或 ~/.config/tavern
def worlds_dir() -> Path: ...               # tavern_home() / "worlds"
def ensure_dirs() -> None: ...              # mkdir -p

# src/tavern/worldpack/install.py
@dataclass
class InstalledWorld:
    id: str
    name: str
    version: str
    path: Path
    installed_at: str
    source: str
    source_type: str
    estimated_tokens: int

def install(source: Path, *, force: bool, skip_validate: bool) -> InstalledWorld: ...
def list_installed() -> list[InstalledWorld]: ...
def uninstall(world_id: str) -> InstalledWorld: ...
```

业务函数返回结构化对象,CLI 层负责渲染,方便未来加 `--json`。

### 5.4 异常语义

- `InstallError(msg, code)` —— 业务失败,code ∈ {"validation", "exists", "not_found", "bad_archive"}
- I/O 硬错误(权限等)—— 让原生 OSError 上抛,由 CLI 转 exit code 2

---

## 六、测试策略

### 6.1 关键测试点

- 三种源都能装(single toml / directory / tar.gz)
- Zip slip 攻击 fixture —— 拒绝含 `../` 路径的归档
- `--force` 语义(覆盖旧版本、绕过校验)
- id 冲突 → 退出 1
- 校验失败 → 退出 1(除非 `--force`)
- `list` 空态 + 单条 + 多条
- `uninstall --yes` 不问 prompt
- `TAVERN_CONFIG_HOME` 隔离:所有测试都不能碰真实 `~/.config/tavern/`

### 6.2 fixture 复用

- `tests/fixtures/full-ok/` —— 目录源
- `tests/fixtures/minimal-ok/world.toml` —— 单文件源
- 归档由测试运行时生成(避免仓库里放二进制)

### 6.3 隔离

conftest 提供 `tavern_home` fixture,自动 `monkeypatch.setenv("TAVERN_CONFIG_HOME", tmp_path)`。

---

## 七、风险与取舍

| 议题 | 决定 |
|---|---|
| 单文件 install 要不要"就地"存单文件? | **不**。规范化为目录,布局与目录源一致,后续无分支 |
| 校验失败允许 `--force`? | **允许**。用户可能明知有 warning/一时想跑,兜底不该越权 |
| `.tavern-installed.toml` 放在世界包目录里,会不会污染? | **不影响**。校验器忽略未知的 dotfile;`.` 开头也不会被 loader 扫到(只扫 `*.toml` 于子目录) |
| Zip slip 防护? | **必须**。所有归档成员在解压前检查 `member.name`,拒绝含 `..` 或绝对路径 |

---

## 八、验收指标

- `tavern install examples/minimal-tavern/world.toml` 后 `tavern list` 看到它
- `tavern uninstall minimal-tavern --yes` 后 `tavern list` 里消失
- 装同 id 两次,第二次退出 1;`--force` 覆盖成功
- 所有测试用 `TAVERN_CONFIG_HOME` 隔离,不污染用户 `~/.config/`
- 单元测试 + CLI 端到端测试全绿

---

## 九、后续联动

- **P2 · LLM 配置向导**:复用 `tavern_home()` 建 `config.toml`
- **P3 · 世界选择器 UI**:直接消费 `list_installed()` 返回
- **P4 · `tavern update <id>`**:读 `.tavern-installed.toml.source` 再 install --force
