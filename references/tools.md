# 工具来源、平台与安全

本Skill用Python标准库编排，实际写入由开源本地工具执行。图片内容校验使用Pillow。没有在线检测服务或远端发布接口。doctor本身没有自动安装器，缺少任务依赖时由Agent通过可信渠道安装并复检。

## 工具

| 工具 | 用途 | 官方来源与许可 |
|---|---|---|
| ExifTool | 读取元数据，写入图片与MP4/MOV的描述字段 | https://exiftool.org/ ，https://github.com/exiftool/exiftool ；按Perl许可条款，具体以发行包LICENSE为准 |
| ffprobe（FFmpeg） | 视频只读检查和逐包哈希 | https://ffmpeg.org/ ；LGPL/GPL取决于构建，https://ffmpeg.org/legal.html |
| MKVToolNix | 提取与写入MKV标签 | https://mkvtoolnix.download/ ；GPL，核对具体发行包 |
| Pillow | 图片逐帧解码及像素校验 | https://pillow.readthedocs.io/ ，https://github.com/python-pillow/Pillow ；核对发行包LICENSE |

免费、开源不等于没有漏洞。安装时核验实际版本、维护状态、安全公告、发行源及可用的签名/校验值，不下载来源不明的整合包，不使用 `curl | sh`。

## 平台选择

- macOS：优先已有版本；Homebrew中 `exiftool`、`ffmpeg`、`mkvtoolnix` 按需安装。Apple Silicon、Intel分别使用本机可信工具，不硬编码 `/opt/homebrew`。
- Windows：ExifTool官方Windows包（保留随包依赖）、MKVToolNix官方包。FFmpeg从官网链接的Windows构建获取并核对来源。使用 `python` 或 `py -3`。
- Linux：优先发行版签名仓库。Debian/Ubuntu常见包名为 `libimage-exiftool-perl`、`ffmpeg`、`mkvtoolnix`；其他发行版以本地仓库为准。不要把其他系统的包名当成通用命令。
- Pillow按当前Python环境安装；建议使用虚拟环境，避免修改系统Python。

运行 `doctor` 只检查，不安装。不在PATH中的工具可用主命令选项 `--exiftool`、`--ffprobe`、`--mkvextract`、`--mkvpropedit` 指定可信绝对路径；选项放在子命令前。ExifTool路径应为可直接执行的程序；Windows按官方包说明准备exiftool.exe。

## 实际安全约束

ExifTool有可执行Perl表达式的选项，且默认可能加载 `.ExifTool_config`。本脚本显式指定本Skill唯一的固定配置 `scripts/exiftool-jk.config`，覆盖默认配置发现；该配置仅声明XMP命名空间，不读取用户文件、不包含用户输入或回调。

用户JSON配置不是ExifTool配置文件，不允许 `-config`、`-if`、`-p`、`-@` 等原始选项。调用使用参数数组、绝对文件路径、`shell=False`。输入文字按值写入，不使用ExifTool的表达式复制语法；不访问URL，不执行现有元数据里的指令。

MKV标签XML保留数据但不加载外部实体；拒绝实体声明及未知DTD。图片/视频依然是需要解析的不可信输入，应使用维护中的工具，在已有工作区权限内运行。

来源：

- ExifTool安全说明：https://exiftool.org/#security
- ExifTool固定配置用法：https://exiftool.org/exiftool_pod.html#config-CFGFILE
- 命名空间定义示例：https://github.com/exiftool/exiftool/blob/master/config_files/example.config
- ffprobe：https://ffmpeg.org/ffprobe.html
- MKV标签：https://mkvtoolnix.download/doc/mkvpropedit.html

本目录只创建本地Skill包。未自动注册到全局Skill目录，也未改变系统或其他项目配置。当前会话可按本目录路径使用；需要全局安装时另行选择安装范围。

## 版本基线

Python 3.10+；ExifTool 13.0+；Pillow 10.4+；FFmpeg/ffprobe 6.0+；MKVToolNix 80.0+。用途和按能力依赖见 [README](../README.md#第三方工具与版本要求)。这是兼容基线，不代表安全背书；使用可信来源的维护版本。安装后立即运行 doctor；缺少任务依赖时由Agent安装，再运行doctor复检。
