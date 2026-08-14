# 酒馆 · 世界观设计文档

> 这份文档教你**从零造一个世界包**:世界的结构长什么样、每个字段该怎么填、什么样的世界更容易讲出好故事、怎么打包分享。
>
> 如果你只想玩已有世界,请看 `USAGE.md`。
> 如果你想了解引擎架构,请看 `DESIGN.md`。

---

## 一、世界包是什么

一个**世界包**是一个可分发的目录(或单个 TOML 文件),把一个可玩世界所需的全部信息封装在一起。

```
my-world/
├── world.toml          # 必须。世界的全部设定
├── intro.md            # 可选。给玩家看的开场引言,支持 Markdown
├── npcs/               # 可选。关键 NPC 的独立卡片
│   ├── shen-shuoshu.toml
│   └── li-jiangjun.toml
├── locations/          # 可选。重要地点
│   └── zuixian-lou.toml
├── templates/          # 可选。玩家角色模板(建角色时的选项)
│   ├── 落魄书生.toml
│   ├── 游侠.toml
│   └── 酒楼小二.toml
└── assets/             # 可选。目前只支持纯文本资源(参考音、术语表、地图 ASCII)
    └── glossary.md
```

**极简版**:只有一个 `world.toml`,就能作为一个世界跑。所有其他文件都是为了让世界更丰满、开局更顺畅。

**打包分发**:把整个目录压成 zip / tar,或者只发单个 `world.toml`,别人 `tavern install <path>` 就能装上。

---

## 二、`world.toml` 完整字段

先看一个**最小可运行**的世界文件:

```toml
[world]
id      = "example-jianghu"
name    = "江湖夜雨"
version = "0.1.0"
author  = "your-name"

[world.setting]
era     = "架空古代武侠"
tone    = "冷峻、克制、以小人物视角讲江湖"

[world.rules]
summary = """
这是一个有武功但无仙术的世界。
金钱、名声、门派立场都非常重要。
主角只是一个普通江湖人,没有开挂能力。
"""

[world.initial_tavern]
name         = "醉仙楼"
location     = "洛阳城·西市"
description  = "老字号酒楼,三教九流杂处,城中消息集散地。"
opening_hook = "你刚坐下,邻桌一个说书人抬眼看了你一下,又低下头。"
```

**这 30 行就能开一局**。下面把每个可扩展字段展开讲。

### 2.1 `[world]` 基础元信息

```toml
[world]
id      = "example-jianghu"      # 全局唯一,建议 kebab-case
name    = "江湖夜雨"              # 玩家看到的世界名
version = "0.1.0"                # 语义化版本
author  = "your-name"
license = "CC-BY-SA-4.0"         # 可选,便于社区二创
tags    = ["武侠", "悬疑", "小人物"]
```

### 2.2 `[world.setting]` 基础设定

```toml
[world.setting]
era        = "架空古代武侠,类唐宋"
geography  = "以中原为核心,东至沿海、西至西域"
tech_level = "冷兵器 + 少量机关术,无火药"
magic      = "无仙术,有武功内力,可传承但不可外传"
races      = "全人类,无异族"
languages  = "官话为主,部分方言"
tone       = "冷峻、克制。多写细节和感官,少写形容词。"
```

**每一个字段都是给 Narrator 的 prompt 素材**。写得越具体,GM 越不容易漂移。**不确定就留空**,别瞎编。

### 2.3 `[world.rules]` 世界规则

这是**最重要的一段**。它告诉 GM"这个世界什么可以发生、什么不能发生"。

```toml
[world.rules]
summary = """
- 武功需要师门传承,不可自学
- 内力伤人可致命,但常人一刀也能致命
- 官府比江湖势力更强,但腐败
- 有轻功但受重力约束,不能长时间凌空
- 医术水平大致等同古代真实水平,重伤难治
"""

# 可选:硬性禁止的东西
forbidden = [
  "现代科技",
  "外星生物",
  "时间穿越"
]

# 可选:世界的"魔法系统"如果存在,写清楚成本和边界
power_system = ""
```

**写规则的关键**:不是要穷尽,是要**画边界**。GM 遇到不确定的情况会保守发挥;只有**你想让玩家惊讶的地方**才需要写死。

### 2.4 `[[world.factions]]` 势力

```toml
[[world.factions]]
id           = "shaolin"
name         = "少林寺"
type         = "武林门派"
influence    = "高"
stance       = "护道"
brief        = "武林正道之首,与官府关系微妙"

[[world.factions]]
id           = "qingbang"
name         = "青帮"
type         = "地下势力"
influence    = "中"
stance       = "利益至上"
brief        = "控制漕运和地下赌场,与朝廷有默契"
```

写 3~5 个主要势力就够,不用穷举。**势力之间的关系**也可以显式声明:

```toml
[[world.faction_relations]]
from = "shaolin"
to   = "qingbang"
type = "敌对"
note = "少林弟子常暗中破坏青帮的漕运"
```

### 2.5 `[[world.timeline]]` 关键历史事件

给这个世界一个**已经发生过的过去**,让玩家开局就有厚度感。

```toml
[[world.timeline]]
when  = "十年前"
event = "少林方丈圆寂,继任之争引发内乱"

[[world.timeline]]
when  = "三年前"
event = "青帮龙头被刺杀,凶手至今未破"

[[world.timeline]]
when  = "去年冬"
event = "洛阳大雪,饿殍遍地,朝廷赈灾不力"
```

这些不需要在故事里明说,GM 会**当作背景**融入叙事(比如 NPC 抱怨、酒馆闲聊、街边告示)。

### 2.6 `[world.initial_tavern]` 初始酒馆

玩家开局的第一个场景,**决定了整个体验的第一印象**。

```toml
[world.initial_tavern]
name          = "醉仙楼"
location      = "洛阳城·西市"
time_of_day   = "戌时(黄昏)"
description   = """
三层木楼,雕花门窗。一楼是散座,二楼有雅间,三楼是掌柜住处。
现在是饭点,楼下坐了七八桌客人,酒菜味混着说书人的醒木声。
"""
present_npcs  = ["shen-shuoshu", "zhang-xiaoer"]   # 引用 npcs/ 下的 id
opening_hook  = """
你推门进来,酒香混着桂花的甜味扑面而来。
角落里,那个自称姓沈的说书人抬眼看了你一下,又低下头。
掌柜张小二从吧台后面招手:"客官,今日想坐哪儿?"
"""
```

**opening_hook 写作要点**:
- 至少提供**一个可交互对象**(人 / 物 / 未解之事)
- 用**感官描写**开场(声音、气味、光线),不要一上来就人物对话
- 不要太多信息,留悬念

**suggestions(可选):开局静态建议**。玩家开局时会看到一行可选的玩家台词;动态场景的其余建议由引擎每回合用 LLM 生成,**你写的这些永远排在最前面**:

```toml
[[world.initial_tavern.suggestions]]
kind = "say"
text = "沈先生,你方才说的'血月'是怎么回事?"

[[world.initial_tavern.suggestions]]
kind = "action"
text = "找个角落坐下,先听听今晚有什么风声"
```

写作要点:
- `kind` 三选一:`say`(说话,展示为 `"…"`)/ `think`(心声,展示为 `*…*`)/ `action`(动作,直接展示)
- `text` 必须是**玩家第一人称**的台词 —— 玩家按 `[1]` 时,这行字就是"玩家说出口的话",会被原样写进存档
- 建议只描述场景中**已存在**的可能性,不要凭空创造新 NPC / 新剧情(玩家选中后 GM 会按它演绎,但世界不该为此长出不存在的东西)

### 2.7 `[world.plot_pacing]` 剧情节奏

控制 Director 什么时候开始"策划剧情"。

```toml
[world.plot_pacing]
honeymoon_turns   = 20    # N1:前 20 回合完全自由,Director 不介入
gentle_turns      = 30    # N1~N1+30:轻推期,偶尔出现小事件
# 之后进入策划期,Director 主动推进主线
```

**参考取值**:
- 轻松日常世界:`honeymoon_turns = 100`,让玩家慢慢熟悉
- 悬疑推理:`honeymoon_turns = 10`,快点抛线索
- 高强度冒险:`honeymoon_turns = 5`,开局就上钩子
- 沙盒探索:两个字段都设得很大,让世界几乎不主动推

### 2.8 `[world.style]` 叙事风格约束(可选)

传给 Narrator 的额外软约束:

```toml
[world.style]
prose_style    = "冷峻克制,少形容词多动作"
sentence_pace  = "短句为主,偶尔长句抒情"
sensory_focus  = "触觉和听觉优先,视觉次之"
forbid_words   = ["其实", "总之", "无论如何"]     # 想避免的口癖
```

---

## 三、NPC 卡怎么写

关键 NPC 建议单独放 `npcs/<id>.toml`。**世界的可信度很大程度靠 NPC 撑起来**。

```toml
# npcs/shen-shuoshu.toml
[npc]
id           = "shen-shuoshu"
name         = "沈先生"
alias        = ["说书人", "沈老"]

[npc.card]
appearance   = "五十来岁,身材瘦长,右手食指有一道旧疤"
personality  = "表面豁达实则谨慎;喝三分酒就爱抖机灵,喝多了就装醉"
speech_style = "半文半白,爱用典故;紧张时会不自觉摸右手食指"

goals        = [
  "找到当年少林内乱中失踪的师弟",
  "活下去",
]

secrets      = [
  "他其实是少林俗家弟子,当年内乱中背叛师门",
  "他知道青帮龙头被杀案的一部分内情",
]

# 与其他 NPC 的关系(可选,写不写都行)
[npc.card.relations]
zhang-xiaoer = "点头之交"
# GM 会自动推断没写的关系

# 玩家开局对他的印象(如果开局在场)
[npc.initial_impression]
description  = "醉仙楼的常客,自称说书人。你听人说他讲的故事真假掺半。"
```

### 3.1 写好一张 NPC 卡的四个要素

1. **目标**:他想要什么?每个 NPC 至少一个,越具体越好("找到失踪的师弟" > "追求真相")
2. **秘密**:他不想让别人知道的事。这是**戏剧张力的来源**
3. **说话习惯**:让 GM 能一致地演他。写一句范例台词最有用
4. **弱点/怪癖**:让 NPC 显得像活人,不是功能性道具

### 3.2 不要写的东西

- **不要写"NPC 对玩家的态度"**:好感度是运行时计算的,你写死了 GM 反而尴尬
- **不要写"NPC 会在 X 情况下做 Y"**:剧本式设计会让 GM 变僵硬。写清楚 NPC 是谁,让 GM 自己判断
- **不要写太多**:一张卡超过 500 字就该考虑拆分或删减。GM 需要留有想象空间

---

## 四、地点怎么写

只有**反复出现或对剧情关键**的地点才需要单独写。次要地点让 GM 现编就行。

```toml
# locations/luoyang-xishi.toml
[location]
id       = "luoyang-xishi"
name     = "洛阳西市"
type     = "城区"

[location.description]
brief    = "洛阳最大的市场,鱼龙混杂"
details  = """
东西约两里,南北一里。
主街两边是永久性店铺,巷子里有临时摊贩。
早晨和黄昏最热闹,午后有小睡的商贩。
夜间不封坊,但巷子里有青帮巡夜。
"""

[location.notable_places]
zuixian-lou   = "醉仙楼(初始酒馆)"
tie-jiang-pu  = "铁匠铺,老板与青帮有关"
```

---

## 五、玩家角色模板

在 `templates/<name>.toml` 里预置几个"人设选项",让新玩家快速开局(3 分钟约束)。

```toml
# templates/落魄书生.toml
[template]
name       = "落魄书生"
tagline    = "屡试不第,身无长物,但眼神干净"

[template.pc]
background = """
你叫{{name}},今年二十有六。
连考三次科举皆不中,盘缠花尽,不敢回乡。
一身青衫已经洗得发白,行囊里只剩几本书和半块干粮。
"""
hp                = {current = 12, max = 12}
attributes        = {金钱 = 3, 精神 = 15}
attribute_tags    = ["熟读经史", "识得字画", "手无缚鸡之力"]
inventory         = ["旧书三本", "半块干粮", "破笔一支"]
starting_location = "醉仙楼"
```

**每个世界建议提供 3~5 个模板**,覆盖不同的开局体验:

- 一个"弱势"角色(如落魄书生),突出成长感
- 一个"能打"角色(如游侠),突出爽感
- 一个"信息型"角色(如小二 / 说书人),突出社交感
- 一个"边缘"角色(如逃犯 / 乞丐),突出压力感

模板里的 `{{name}}` 会在建角色时被玩家填的名字替换。

---

## 六、开场引言(intro.md)

`intro.md` 是玩家**选中你的世界后、真正开始游戏前**看到的一段引言,支持 Markdown。

用途:
- 交代世界背景
- 建立氛围
- 说明这个世界的"玩法特点"(是慢节奏日常 / 高强度冒险 / 悬疑推理…)

**长度控制在 500 字以内**,玩家没耐心读完一大篇。举例:

```markdown
# 江湖夜雨

大唐盛世的余晖还未散尽,江湖已经开始下雨了。

十年前少林内乱,武林失去了它的定盘星。三年前青帮龙头被刺,漕运至今混乱。
去年冬洛阳大雪,街边冻死的人比往年多了三倍。

你不是任何人的救世主。你只是一个普通人,想在这个越来越冷的世道里活下去。
运气好的话,或许能顺便解开一两个谜团 —— 但更可能,你会先被卷进去。

**这个世界的特点**
- 节奏偏慢,前 20 回合基本是你自己在探索
- 没有开挂,一刀能死,慎战
- NPC 有自己的目的,不会围着你转
```

---

## 七、造世界的方法论

除了字段填法,这里有一些**心法**:

### 7.1 从"一句话"开始

最好的世界都能用一句话概括:
- 江湖夜雨:**一个褪色的武侠世界,你只是个想活下去的普通人**
- 深海回声:**你是一名深海油井上的工人,同事们开始互相怀疑**
- 樱花下的谎:**你是转校生,班上每个人都有秘密,包括你**

**先写这一句**,再展开细节。展开时不断问"这一条符合那一句吗?"

### 7.2 冲突,而不是设定

新手常常在 "era/geography/technology" 上花很多字,但**世界最重要的是冲突**。

好的世界总是能回答:
- 谁在跟谁作对?
- 他们各自想要什么?
- 为什么现在很紧张?

`[[world.factions]]` 和 `[[world.timeline]]` 是承载冲突的地方,不要跳过。

### 7.3 留白

**不要把每个角落都写满**。GM 需要空间去创造:
- 你写了洛阳西市,你没写北市,GM 会自己编北市的样子
- 你写了少林和青帮,你没写第三个势力,GM 需要时会自己编一个

**规则里明确写下的东西是硬约束,没写的都是 GM 的自由**。用这个原则来决定哪些字段填、哪些留空。

### 7.4 玩几遍再发布

写完 `world.toml`,自己至少完整玩过一次(最好走到策划期,50+ 回合)。你会发现:
- 某些 NPC 卡的秘密永远推不出来 —— 加钩子
- 某个规则和实际游戏冲突 —— 修改
- 开局钩子玩家 3 回合就忘了 —— 重写

**从玩家的实际体验倒推设定**,比拍脑袋写更靠谱。

### 7.5 版本化

`world.toml` 里的 `version` 不是摆设。**修改世界包时更新版本号**,让下载过的玩家知道有更新。用 SemVer:
- Patch(0.1.0 → 0.1.1):修错别字、微调 NPC 卡
- Minor(0.1.0 → 0.2.0):加了 NPC / 势力 / 模板
- Major(0.1.0 → 1.0.0):世界规则变了,老存档可能不兼容

---

## 八、验证你的世界包

写完之后,检查前跑一下:

```bash
tavern validate ./my-world/
```

它会检查:
- TOML 语法是否正确
- 必填字段是否齐全(`world.id/name/setting/initial_tavern`)
- 引用完整性(`present_npcs` 里的 id 是否都在 `npcs/` 下存在)
- 字段长度是否合理(单个字段太长会警告)
- Prompt 预估 token 数(太长的世界会烧钱且降低 GM 表现)

---

## 九、分享你的世界

### 9.1 单文件分享

如果你的世界包只有 `world.toml`,直接把这个文件发给别人:

```bash
tavern install ~/Downloads/some-world.toml
```

### 9.2 目录分享

如果有 NPC / 模板等子目录,压缩后分享:

```bash
tar czf my-world.tar.gz my-world/
# 对方
tar xzf my-world.tar.gz
tavern install ./my-world/
```

### 9.3 通过社区索引

主项目会维护一个 **world index 仓库**(建设中),把你的世界包 PR 进去,别人可以:

```bash
tavern search 武侠
tavern install jianghu-yeyu
```

### 9.4 授权

推荐用 **CC-BY-SA-4.0** —— 允许自由改编、必须署名、衍生作品必须同样开放。让世界像故事一样,能被不断改写下去。

---

## 十、示例:一个可运行的极简世界

放在 `examples/minimal-tavern/world.toml`,作为你的起点参考:

```toml
[world]
id      = "minimal-tavern"
name    = "无名酒馆"
version = "0.1.0"
author  = "tavern-team"

[world.setting]
era  = "架空"
tone = "开放式,任何题材都可能"

[world.rules]
summary = "这是一个几乎没有预设规则的世界,一切由玩家和 GM 共同塑造。"

[world.initial_tavern]
name         = "无名酒馆"
location     = "十字路口"
description  = "一间小酒馆,你不记得自己是怎么来的。"
opening_hook = "你在酒馆里醒来,桌上有一杯温热的酒。你不记得自己是谁,也不记得来这里做什么。"

[world.plot_pacing]
honeymoon_turns = 5
gentle_turns    = 15
```

**5 秒创建、20 分钟游戏**。改一改就是你的第一个世界。

---

## 十一、下一步

- 想玩一玩你造的世界?看 **`USAGE.md`**
- 想改引擎、加新功能?看 **`DESIGN.md`**
- 造出了得意的世界?分享到社区仓库,让更多人推开你的那扇门

好世界不是设计出来的,是**被玩出来的**。开始写吧,写坏了删掉重来就是。
