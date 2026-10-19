# JK Media Metainfo

修改图片与视频的描述性元数据：先预检，列出完整修改清单，经用户确认后写入。

这个Skill用于维护标题、描述、创作者、来源网址、署名、许可、系列、项目和素材编号等信息。你可以用自然语言交互，也可以提供JSON配置。AI帮助理解要求和查看画面，实际写入由本地开源工具完成。

**预检不是AI生成鉴定。** 没有AI标识不能证明是实拍；画面写实也不代表照片真实。遇到无法判断的内容，保留“未知”，先补充来源依据。

## 目录

1. [适用范围与保护边界](#1-适用范围与保护边界)
2. [工具与安装](#2-工具与安装)
3. [快速开始](#3-快速开始)
4. [内容预检规则](#4-内容预检规则)
5. [自然语言与终端交互](#5-自然语言与终端交互)
6. [配置文件使用](#6-配置文件使用)
7. [常见场景](#7-常见场景)
8. [输出与失败处理](#8-输出与失败处理)
9. [安全与限制](#9-安全与限制)
10. [目录和实施状态](#10-目录和实施状态)

## 1. 适用范围与保护边界

| 可编辑 | 保护范围 |
|---|---|
| 标题、描述、图注、关键词 | 图片像素、画面方向、颜色、透明通道、动画帧 |
| 作者、编辑者、贡献者及来源署名 | 分辨率、ICC、DPI、相机参数、GPS、原始拍摄时间 |
| 来源网页、原图网址、作者主页、许可链接 | 视频编码、音视频数据、时序、音轨、字幕轨 |
| 版权说明、使用条款 | 章节、封面附件、来源凭证与签名 |
| 项目、系列、素材ID、页码、版本、评级 | 原文件保持不变，只生成副本 |
| 真实有据的AI制作说明 | 不生图、不修图、不转码、不替换媒体内容 |

“只改元数据”不是“整个文件字节不变”。元数据本来就是文件的一部分，写入后文件大小和完整文件SHA256可以变化，视频容器的总平均码率也可能受文件大小影响；媒体内容和受保护的技术属性须保持不变。

### 当前格式支持

| 格式 | 默认处理方式 |
|---|---|
| JPEG、PNG、TIFF、WebP、GIF | ExifTool写入副本；Pillow逐帧内容校验 |
| MP4、MOV、M4V | ExifTool写入副本；ffprobe核对全部轨道和逐包数据 |
| MKV | MKVToolNix标签编辑；ffprobe核验；保留其他标签 |
| HEIC、HEIF、AVIF、WebM、AVI、WMV、其他 | 当前仅显式选择旁车JSON |

支持嵌入不代表所有字段都能出现在系统“文件属性”或播放器界面；最终以本工具读回为准。详见 [格式能力与校验方法](references/formats.md)。

## 2. 工具与安装

先进入安装后的 Skill 目录，不依赖开发者机器的固定路径。

### Agent 与系统兼容

支持 WorkBuddy、Codex、Claude Code 等能读取 `SKILL.md` 并运行本地 Python 的 AI Agent；执行逻辑不依赖某个 Agent 的专有 API。支持 Windows、macOS、Linux 的路径与工具发现。跨平台代码兼容不代表已在三个系统和全部 Agent 上实测。

将整个目录（包括 scripts、references、agents）放入宿主文档规定的 Skill 目录，或在会话中提供 `SKILL.md` 的绝对路径。各宿主的自动发现位置不同，不猜测或修改其全局配置。

### 安装本 Skill

仓库：[jackywjj/jk-media-metainfo](https://github.com/jackywjj/jk-media-metainfo)。下载仓库ZIP并解压，或使用已安装的Git获取：

```bash
git clone https://github.com/jackywjj/jk-media-metainfo.git
```

确保最终结构为 `jk-media-metainfo/SKILL.md`、`scripts/`、`references/`、`config/` 等，不能只复制SKILL.md，也不要多嵌套一层同名目录。

- **Codex**：可直接在对话中要求“安装这个仓库的Skill：https://github.com/jackywjj/jk-media-metainfo ，安装后读取SKILL.md并执行环境预检”。本机已有Skill安装器时由Agent使用；也可提供解压后SKILL.md的绝对路径，先在当前会话使用。
- **Claude Code**：将整个目录放到用户级 `~/.claude/skills/jk-media-metainfo/`（Windows为 `%USERPROFILE%\.claude\skills\jk-media-metainfo\`），或项目级 `.claude/skills/jk-media-metainfo/`。新会话可输入 `/jk-media-metainfo`。[官方安装位置说明](https://code.claude.com/docs/en/skills)。
- **WorkBuddy**：在对话中提供仓库链接或解压后的完整目录，要求“将此Skill安装并启用，保留完整脚本与配置模板，安装后执行环境预检”。按当前版本的技能管理入口检查是否启用；未识别时直接提供SKILL.md绝对路径。[官方技能指南](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market)。

已有同名安装时先保留旧版本及个人 `config/metadata.json`，不要直接覆盖；安装后让Agent报告实际安装目录。新会话验证能找到 `jk-media-metainfo`，且可读取其脚本与配置模板。提供路径使用只代表当前会话可用，不等于已全局安装。

**安装完成后，安装 Agent 必须立即运行一次 `doctor`，展示版本、缺失工具和可用能力；首次使用、更换 Python 或升级工具后再运行。** 普通文件复制没有通用安装钩子，手动安装者应执行下列命令；只有实际运行过才能报告预检完成。

```bash
python3 scripts/media_metainfo.py doctor
```

Windows PowerShell 使用 `py -3 scripts/media_metainfo.py doctor`（或 `python`）；macOS/Linux 使用 `python3`。后续命令中的解释器也应保持一致。

### 第三方工具与版本要求

以下为本 Skill 的兼容基线，不是最新版本或安全无漏洞保证。优先使用官方仍维护、已修复安全问题且与 Python 兼容的版本。doctor 逐项给出 minimum、detected、ok，并分别报告图片、视频、MKV、旁车能力；`partial` 表示部分功能可用，不能报告全部环境满足。

| 工具 | 最低版本 | 何时需要 |
|---|---|---|
| Python | 3.10 | 所有命令 |
| ExifTool | 13.0 | 完整元数据预检、图片及 MP4/MOV/M4V 嵌入 |
| Pillow | 10.4 | 图片嵌入后的逐帧校验；安装与 Python 匹配的版本 |
| ffprobe（FFmpeg） | 6.0 | 视频嵌入后的完整数据核验 |
| ffmpeg（FFmpeg） | 6.0 | 可选，仅抽取视频预览帧 |
| mkvextract、mkvpropedit（MKVToolNix） | 80.0 | MKV 嵌入 |

`doctor` 命令本身只检查，不安装、不联网、不修改配置。Agent发现缺少本次任务所需软件时，应自行按下述可信渠道安装；低于基线时更新，版本未知先查明。只安装所需组件，Pillow优先放在独立虚拟环境。安装后使用同一Python和工具路径重跑doctor，确认相应能力满足再继续。Python缺失时先安装Python。遇到管理员权限或宿主审批，按实际要求申请；失败时说明原因，不绕过权限。发现已知漏洞或可疑来源应提醒用户，并选择可信的修复版本。旁车可在仅有 Python 时使用，但缺少 ExifTool 的元数据检查仍不完整。

### macOS

已有Homebrew时，Agent按本次任务缺失项选择安装：

```bash
brew install exiftool
brew install ffmpeg
brew install mkvtoolnix
```

图片校验若缺少Pillow，可放在本目录独立虚拟环境：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install Pillow
.venv/bin/python scripts/media_metainfo.py doctor
```

已有Pillow时无需重复安装。实际执行脚本应始终使用装有Pillow的同一个Python环境。

### Windows

从 [ExifTool官网](https://exiftool.org/)、[MKVToolNix官网](https://mkvtoolnix.download/)获取对应Windows发行包；FFmpeg使用 [官网列出的Windows构建来源](https://ffmpeg.org/download.html)。保留官方包中必需的配套文件。可加入PATH，也可通过工具路径选项调用。

### Linux

优先发行版的签名软件仓库。Debian/Ubuntu常见示例为：

```bash
sudo apt install libimage-exiftool-perl ffmpeg mkvtoolnix python3-pil
```

其他发行版使用自己的包名和包管理器。安装前核对当前包来源、版本及安全公告。

### 指定已有工具路径

所有工具路径选项必须在子命令之前：

```bash
python3 scripts/media_metainfo.py --exiftool "/可信路径/exiftool" precheck "/素材目录/图片.png"
```

同样支持 `--ffprobe`、`--ffmpeg`、`--mkvextract`、`--mkvpropedit`。路径仅指可信本机程序；不得提供下载链接或任意命令字符串。

## 3. 快速开始

### 单文件与目录批量

```bash
python3 scripts/media_metainfo.py precheck "/素材目录/图片.png"
python3 scripts/media_metainfo.py precheck "/素材目录" --report "./batch-precheck.json"
python3 scripts/media_metainfo.py precheck "/素材/01.jpg" "/素材/02.mp4"
```

目录会筛选已支持扩展名的图片和视频（含大写扩展名），忽略其他文件与子目录。配置 `inputs` 同样可写目录，例如 `"inputs": ["./media"]`。预检报告包含每个文件的 SHA256，配置仍须在 `per_file` 中逐个绑定内容审阅记录；不会用一个文件的审阅代替整批。

**单批硬上限512个文件，串行处理。** 发现第513个即拒绝整批，在读取媒体内容或写入前停止，不静默截取，也不自动发起下一批。超限请明确拆分输入；目录内容变化可能导致 apply 重新计划时拒绝。512是数量限制，不能保证超大视频或复杂动画不会耗尽资源；保留工具超时和失败停止策略。重复输入与输出同名仍会拒绝。终端 `interactive` 保持单文件；Agent 可根据批量预检生成配置。

### 第一步：只读预检

```bash
python3 scripts/media_metainfo.py precheck "/素材目录/图片.png" --report "./precheck.json"
```

输出包括：

- 原文件SHA256、大小、图片／视频类型。
- 当前描述性字段及工具可读取的原始元数据。
- 已有AI来源声明或提示词线索；它们可能是写入者声明，不是鉴定结论。
- 是否检测到来源凭证标识；依赖缺失时显示未知。
- `review_template`：待填的内容预检记录。

`inspect`同样可以读取这些信息。两者均不修改原文件。

### 第二步：完成内容预检

查看图片、视频代表性帧及来源资料。将 `review_template` 中的分类、人物范围和依据填好，保留当前文件的SHA256。

```json
{
  "kind": "mixed",
  "people_scope": "mixed",
  "basis": "visual",
  "evidence": "左侧为注明来源的真实照片，右侧为标明AI造型的想象图，整张为拼图。",
  "input_sha256": "从本文件预检结果复制的64位校验值"
}
```

不要照抄别的文件的校验值。图片发生变化后，预检记录会失效。

### 第三步：准备配置并查看差异

参考 [配置示例](examples/metadata.json)，填写自己的文件路径、字段和预检记录：

```bash
python3 scripts/media_metainfo.py plan "./metadata.json" --report "./plan-report.json"
```

只有 `ready: true` 才能写入。存在缺失依赖、人物分类冲突、未知字段、过期SHA256或输出重名时，会显示原因。

### 第四步：执行修改

```bash
python3 scripts/media_metainfo.py apply "./metadata.json" --report "./apply-report.json"
```

运行 `apply` **之前必须先展示完整修改清单，等待用户明确确认**，即使用户已提供JSON或最初说了“帮我修改”。清单包括实际输入文件与数量、输出位置、嵌入／旁车方式，以及用户要求的全部字段：中文名、配置键、当前值、新增／替换／删除操作和目标值。批量公共字段注明适用文件，逐文件差异全部列明；较长时附完整可读清单，不截断。不支持或缺少依据的要求也列出原因，先解决阻断项再确认。

确认同一份清单后整批执行，不逐文件重复询问。文件范围、内容SHA256、字段、目标值、输出位置或存储方式变化时，更新清单并重新确认。执行前核对文件列表和SHA256与确认时一致。`apply`会重新预检，写入副本并读回，原件不覆盖。该确认流程由Agent执行；纯终端直接调用apply不会弹出确认。

**示例里的网址和校验值只用于说明格式，不是任何实际素材的来源或预检结果。** 替换后再使用。

## 4. 内容预检规则

### 内容类别

| kind | 含义 | 人物相关字段规则 |
|---|---|---|
| photo | 有依据的真实拍摄，包括真实景物 | 真实人物须另外声明people_scope=real；无人物的实拍可填none |
| ai_generated | AI生成或以AI重构为主的画面，包括写实AI人像 | 不写真人身份、本画面摄影师、模特授权 |
| illustration | 动漫、卡通、手绘、插画、虚构人物表现 | 角色写fictional_characters，不写真人身份 |
| mixed | 真照片与AI、插画或其他素材混合，或真假对照图 | 整张按受限素材处理；来源作者写source_credits |
| non_person | 没有人物的素材，且未作为真实拍摄分类 | 不写画面中的真人 |
| unknown | 证据不足，尚未完成分类 | 阻断写入，先补充依据 |

`people_scope` 必须另外填写：`real`（真实拍摄的人）、`fictional`（虚构／合成人物）、`mixed`（混合）、`none`（无人物）、`unknown`（未知）。

`basis` 填 `user`（用户声明）、`visual`（视觉检查）、`provenance`（来源记录）。证据说明应准确表述“谁提供了什么依据”。看到皮肤光滑、六根手指等现象只能作为怀疑，不能给出伪造的AI置信度或鉴定证书。

### 哪些叫“真人相关元数据”？

本Skill限制：

- `depicted_real_people`：画面中真实拍摄的人物身份。
- `photographer`：本画面的实拍摄影师。真实景物照片也可有摄影师；AI造型或动漫作品不使用这个字段。
- 人物细节、模特授权编号／状态：首版只允许明确清理已有错误字段，不允许创建授权声明。

**作者是现实中的人，不等于画面中是真人。** 动漫图片可以保留真实插画师姓名；AI作品可以保留真实编辑者；AI参考照片仍应保留摄影师署名及许可。它们分别放在 `creator`、`editor`、`source_credits` 等字段。

### 这批历史人物选角图如何处理？

例如左侧是胡军真实照片，右侧是AI古装造型：

- 内容类别为 `mixed`，人物范围为 `mixed`。
- 标题和描述可说明“胡军选角对照、AI造型想象”，不能声明演员实际参演。
- 不将整张图登记为“胡军真人拍摄的郑成功剧照”。
- 不添加 `depicted_real_people` 或整张图的实拍摄影师字段。
- 原照片作者、CC许可、来源网页、裁切及AI改编说明放 `source_credits` 等来源字段。
- “郑成功”作为想象角色使用 `fictional_characters` 或描述说明，避免伪装成历史容貌实录。

对视频检查代表性帧只能证明抽查部分；有AI镜头、动漫段落或来源不明片段时，整段使用mixed或保持unknown。命令行工具不会自动做视觉识别，Skill需要实际查看画面或取得用户可靠说明。

### 已有错误字段怎么办？

预检不会偷偷删除。若动漫图已有真人身份字段，会要求在 `remove` 中明确列出：

```json
{
  "remove": ["depicted_real_people", "photographer", "model_release_id", "model_release_status"]
}
```

这是配置片段，需放入完整配置。其他私有标签中的错误信息可能需要单独审阅；不要把自动规则理解为已检查所有隐私或版权信息。

## 5. 自然语言与终端交互

### 触发词与示例

使用“修改图片／视频元数据”“批量设置 metadata”“修改 EXIF／XMP／IPTC”“设置作者、版权、来源、标题、描述、关键词”“清除指定元数据”等表达即可触发。主要目的为修改元数据，内容预检是保护步骤；只读查看也可使用。技术字段如GPS、拍摄时间不在可修改范围。

### 在 WorkBuddy、Codex、Claude Code 中使用

在当前会话中可直接说：

> 使用项目下 jk-media-metainfo/SKILL.md。先预检这几张图，区分真人、AI和动漫，再把作者写为指定姓名，补充我提供的来源网址。给我看修改差异，生成副本。

也可以提出：

> 这张是动漫插画，作者是我提供的插画师。不要填写画面中的真人，保留来源署名，用角色名称和作品系列信息。

Skill会将要求整理成同一套JSON配置，运行本地工具。必要信息缺失时询问；不会从看起来相似的脸推测真实身份或自行补造许可。

本目录没有自动安装到全局Skill发现目录。如果新会话无法通过 `$jk-media-metainfo` 找到它，先提供本目录 `SKILL.md` 的绝对路径即可。

### 纯终端交互

```bash
python3 scripts/media_metainfo.py interactive "/素材目录/图片.png" \
  --save-config "./我的修改.json" \
  --output-dir "./output"
```

依次输入类别、人物范围、依据、`set` JSON对象、`remove` JSON数组。程序把当前SHA256写入配置，保存配置后退出，不马上写入媒体。然后运行：

```bash
python3 scripts/media_metainfo.py plan "./我的修改.json"
python3 scripts/media_metainfo.py apply "./我的修改.json" --report "./我的修改结果.json"
```

终端模式不含AI视觉模型，需要你自己查看画面并填写分类。`--storage sidecar` 可用于生成配套记录。

## 6. 配置文件使用

### 固定配置的位置

以下 `SKILL_DIR` 指**实际安装目录**，不是素材目录或当前终端目录。

| 文件 | 作用 | 是否自定义 |
|---|---|---|
| `SKILL_DIR/config/metadata.example.json` | 随Skill提交的基础模板 | 建议保留原样，复制后修改 |
| `SKILL_DIR/config/metadata.json` | 个人固定配置，每次复用的字段与本次输入 | 可以；已被.gitignore忽略，不提交个人路径和来源信息 |
| `SKILL_DIR/examples/metadata.json` | 已有单张插画的完整教学示例 | 参考用，不作为默认配置 |
| `SKILL_DIR/scripts/exiftool-jk.config` | 固定的ExifTool命名空间与安全配置 | 不替换、不填写个人内容，不接受外部Perl配置 |

安装／首次使用时，若个人固定配置不存在，让Agent从模板复制为 `config/metadata.json`；若已存在则保留，不覆盖。模板含占位路径，不能直接用于实际写入。

macOS/Linux，在Skill目录执行：

```bash
# 仅在目标文件不存在时复制
cp -n config/metadata.example.json config/metadata.json
```

Windows PowerShell，在Skill目录执行：

```powershell
if (-not (Test-Path "config/metadata.json")) {
    Copy-Item "config/metadata.example.json" "config/metadata.json"
}
```

### 自定义并复用固定配置

1. 编辑 `config/metadata.json` 的 `set`，填写固定作者、版权、来源、项目及关键词等；不需要的键直接从配置中移除，表示保留媒体现值。需要清除媒体字段时把键名写进 `remove`，不能用空字符串冒充删除。
2. 每次任务更新 `inputs`（文件或目录）和 `output_dir`，推荐素材使用绝对路径。相对路径始终基于 **config目录**，因此模板中的 `../output` 指Skill根目录下的output。Windows JSON路径使用 `C:/素材/图片.jpg` 或双反斜杠，不用单反斜杠。
3. 根据本批 `precheck` 结果填写 `per_file`：每个文件的path、类别、人物范围、依据、当前SHA256。固定的公共字段可以复用，旧文件审阅记录不能套到新文件；单文件可使用顶层review。
4. 告诉Agent：“使用已安装 jk-media-metainfo 的固定配置 config/metadata.json 处理本批素材。先列出完整修改清单，等我确认后执行。”用户本次明确要求优先；有冲突时更新配置并在清单中列明，不默默使用旧值。Skill作者Jacky不会自动成为媒体作者。
5. 确认后写入并读回。再次运行前换新的输出目录，避免与已有结果重名。

CLI始终显式传入配置路径，**脚本不会自动搜索、加载或合并固定配置**。Agent未收到其他配置路径时，优先检查上述固定位置；若用户指定了其他JSON，只使用用户指定文件。

```bash
python3 scripts/media_metainfo.py precheck "/素材目录" --report "./precheck.json"
python3 scripts/media_metainfo.py plan "./config/metadata.json" --report "./plan.json"
# 阅读完整清单并确认后，再执行下一条
python3 scripts/media_metainfo.py apply "./config/metadata.json" --report "./apply.json"
```

Windows将python3替换为 `py -3` 或当前环境的python。示例报告名已存在时请更换；程序不会覆盖。升级或重新安装前单独备份个人固定配置，升级后恢复并核对字段兼容性，不直接把新模板覆盖个人配置。

### 完整结构

```json
{
  "version": 1,
  "inputs": ["./media/01.png", "./media/02.png"],
  "output_dir": "./output",
  "storage": "embedded",
  "set": {
    "creator": ["茶馆主理人"],
    "project": "历史人物选角",
    "keywords": ["历史人物", "创意选角"]
  },
  "remove": [],
  "per_file": [
    {
      "path": "./media/01.png",
      "review": {
        "kind": "illustration",
        "people_scope": "fictional",
        "basis": "user",
        "evidence": "素材作者提供的动漫插画，用户已确认来源。",
        "input_sha256": "替换为01.png实际SHA256"
      },
      "set": {
        "title": "历史人物插画",
        "fictional_characters": ["作品中的角色名称"]
      }
    },
    {
      "path": "./media/02.png",
      "review": {
        "kind": "mixed",
        "people_scope": "mixed",
        "basis": "visual",
        "evidence": "查看整张图，包含真实参考照片和AI造型，两部分有明确标注。",
        "input_sha256": "替换为02.png实际SHA256"
      },
      "set": {
        "title": "真人参考照片与AI造型对照",
        "source_url": "https://example.com/photo-source",
        "source_credits": "按真实来源填写摄影师、许可证、来源链接及改动说明。"
      },
      "remove": ["depicted_real_people"]
    }
  ]
}
```

### 配置约定

| 配置项 | 规则 |
|---|---|
| version | 当前为1 |
| inputs | 本地图片／视频文件或目录的列表；目录只扫描当前层，不递归、不展开通配符；合计最多512个媒体文件 |
| output_dir | 独立输出目录 |
| storage | embedded嵌入副本；sidecar仅生成JSON |
| set | 所有文件通用的字段 |
| remove | 明确删除的白名单字段 |
| review | 单文件时可放顶层；不同文件使用per_file绑定各自SHA256 |
| per_file | 单文件覆盖；path必须唯一且出现在inputs中 |

- 相对路径以**配置文件所在目录**为基准，不是终端当前目录。
- `per_file.set` 覆盖同名公共字段；`remove`合并。
- 同一字段不能同时set和remove。
- 字符串数组会替换整个目标列表，未指定的字段保留。
- null、空字符串、空数组不会被当作删除，会拒绝。
- 不支持任意原始工具参数、ExifTool表达式或可执行配置。
- URL必须为HTTP(S)，不能含用户名和密码；不要填写带token的临时链接。
- 不同目录的同名输入会输出重名，需拆分配置或输出目录。
- 详情及完整字段见 [字段映射](references/fields.md)。

### 原图网址与来源网页的区别

- `source_url`：原图所在页面，便于查阅作者与许可。
- `original_image_url`：原图文件地址。
- `reference_urls`：其他资料、历史来源等网址数组。
- `creator_url`：作者网站。
- `license_url`：权利说明或许可证页面。

写入这些地址不会在图片画面里生成文字、二维码，也不会自动在微信正文里显示链接。

## 7. 常见场景

### 动漫插画

预检为 `illustration/fictional`；允许创作者、来源、系列、角色名，禁止添加真人身份和实拍摄影声明。

### AI写实人像

即使看起来像真实照片，按 `ai_generated/fictional` 处理。可用 `ai_note` 说明生成及编辑事实；未知模型版本不填写。不能借元数据把它包装成真实摄影作品。

### 真实人物照片

有拍摄来源依据时使用 `photo/real`。可填写有依据的 `depicted_real_people` 和 `photographer`；姓名必须由用户或来源提供。模特授权声明不在首版新增能力内。

### 真实风景照片

使用 `photo/none`。可保留实际摄影师，不能填写“画面中的真人”。

### 视频与混合素材

先检查来源和代表性帧。有合成或动漫片段时按mixed受限处理。只修改全片描述信息，不改轨道语言、章节、字幕、封面附件或编码参数。

### 无法可靠嵌入、已有签名或暂不安装工具

显式选择：

```json
{
  "storage": "sidecar"
}
```

旁车文件保存原件SHA256、预检记录和修改意图。它**不会改变媒体内部已有字段**，例如sidecar中的remove不能清除图片本身的错误真人信息。分享媒体时要一起传递旁车文件，接收软件也未必自动识别。

没有ExifTool时，读取报告会标记预检不完整。旁车可保存用户审阅后的记录，但不能声称已排除图片内的AI标识、真人字段或来源凭证。

## 8. 输出与失败处理

### 输出状态

| 状态 | 含义 |
|---|---|
| plan中的ready=true | 修改计划可执行；尚未写入 |
| embedded_verified | 副本已写入，字段读回和媒体保护核验通过 |
| sidecar_saved | 只保存旁车，媒体内没有写入 |
| failed_unverified | 执行或核验失败，输出副本不能当成成品 |
| refused／ready=false | 拒绝或存在阻断项 |

嵌入输出保留原文件名；旁车输出为 `原文件名.metadata.json`。MKV还会保留本次写入使用的 `.tags.xml`。报告包含修改字段和输出路径；它可能含作者、网址等信息，分享前按需要检查。

### 常见问题

**报“需要完成内容预检”**：补全kind、people_scope、basis、evidence及当前SHA256。

**报“预检缺少SHA256或文件已变化”**：重新执行precheck，不绕过绑定检查。

**报“AI/动漫/混合素材不能添加真人身份”**：检查字段含义，把原参考照片的作者放source_credits，角色放fictional_characters；不要为通过检查伪改分类。

**已有字段与分类冲突**：用明确的set修正内容分类字段，或在remove中清理已有错误真人字段。脚本不擅自删除。

**字段在资源管理器里看不到**：系统属性面板不一定展示XMP自定义字段。用本脚本inspect读回；不要以面板未显示断言写入失败。

**输出文件或报告已存在**：换一个本次运行目录或新的报告文件名。程序不自动覆盖或批量删除。

**某一文件执行失败**：整批计划阶段有问题则不开始写；执行阶段失败则停止后续文件，已成功结果保留。失败副本及报告留作核对，不自动删除。报告保存失败也不代表媒体未写入，应先inspect已有副本再决定后续操作。

**视频校验耗时较长**：逐包检查需要读取完整文件，工具单次上限900秒。超时就是未完成核验，不用“时长一样”替代。

**上传微信后字段不见了**：平台可能处理文件。原图写入成功、平台素材保留、读者下载版本保留是三个不同层次，需要分别取回核验。本Skill只负责本地处理，不自动上传或更新草稿。

## 9. 安全与限制

- 使用官方发行源或可信签名仓库；开源免费不等于没有漏洞。
- ExifTool部分参数能执行代码，脚本仅使用固定白名单与本Skill审阅过的命名空间配置，禁用默认外部配置发现，不接受用户Perl配置。
- 使用参数数组而非拼接命令；文本、文件名、网址及原元数据都当作数据处理。
- 用户声明仍需真实可信。程序能阻断已声明的动漫类别写入真人字段，但不能防止用户把动漫谎报为实拍，也不能从一个姓名验证本人身份。
- 来源凭证检测有边界。已识别签名仅支持旁车；不会删除、伪造或重新签名C2PA凭证。
- 不联网鉴定、不自动打开来源网址、不上传素材、不操作公众号草稿箱。
- 不批量删除，不覆盖原件，不更改其他项目配置。

工具来源、许可和平台说明见 [tools.md](references/tools.md)。

## 10. 目录和实施状态

```text
jk-media-metainfo/
├── SKILL.md
├── README.md
├── config/
│   ├── metadata.example.json  # 提交的模板
│   └── metadata.json          # 本地个人配置，不提交
├── agents/openai.yaml
├── scripts/
│   ├── media_metainfo.py
│   └── exiftool-jk.config
├── references/
│   ├── fields.md
│   ├── formats.md
│   └── tools.md
└── examples/
    └── metadata.json
```

当前版本：0.2.0。本Skill在本项目目录维护，通过路径使用，不自动安装全局副本。Python负责参数和安全规则，ExifTool/MKVToolNix负责写入，Pillow/ffprobe负责保护核验。

当前机器为macOS Apple Silicon。具体依赖是否可用以doctor为准；Windows/Linux安装方案不代表已经在这两种系统运行验证。实际完成的本地使用记录另见 `IMPLEMENTATION-STATUS.md`，不要把代码中声明的能力当作所有格式已实测。

官方资料：

- [ExifTool工具与安全说明](https://exiftool.org/)
- [ExifTool格式能力](https://exiftool.org/exiftool_pod.html)
- [ExifTool自定义命名空间示例](https://github.com/exiftool/exiftool/blob/master/config_files/example.config)
- [ffprobe文档](https://ffmpeg.org/ffprobe.html)
- [MKVToolNix标签编辑](https://mkvtoolnix.download/doc/mkvpropedit.html)
- [IPTC照片元数据标准](https://www.iptc.org/std/photometadata/specification/IPTC-PhotoMetadata)
- [Pillow文档](https://pillow.readthedocs.io/)
