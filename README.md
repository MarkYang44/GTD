# Multiple_Video_Downloader

YouTube + Instagram + Bilibili 视频与多格式音频批量下载工具。

这是一个基于 [yt-dlp](https://github.com/yt-dlp/yt-dlp) 的程序，支持**命令行**和**网页**两种使用方式。它可以在同一批任务中自动识别 YouTube、Instagram 和 Bilibili 链接，预览播放列表、合集与分 P，既能下载视频，也能按用户选择输出 **MP3 V0 / 源 FLAC / 原始音频 / WAV PCM**。最终文件统一保存到项目内的 `downloads/` 文件夹。

## 功能

- 一次输入多个 YouTube、Instagram 与 Bilibili 链接
- 一批任务最多同时处理 3 个链接，超过上限的任务自动排队
- 三个平台的链接可以任意混合，程序自动识别平台
- 提交前预览并选择播放列表、合集与分 P 条目；每批最多选择 100 项
- YouTube 自动选择可用的最高画质与最高音质
- 音频模式选择源站可获取的最高质量音轨，可输出 MP3 V0、真实源 FLAC、原始音频或 WAV PCM
- 音频文件自动嵌入视频封面；没有封面时仍正常输出音频
- Instagram 支持 Reels、视频帖子、IGTV 和有效期内的 Stories
- Bilibili 支持 `BV`、`av`、移动端视频、分 P 链接和 `b23.tv` 短链接
- Bilibili 大于 50 MiB 的文件可在源站返回的最多 4 个 CDN 主机间自适应测速；aria2c 极速模式为可选功能
- 使用 FFmpeg 合并音视频并输出 MP4，或处理 MP3 / FLAC / WAV 音频
- **命令行模式**：交互式输入和命令行参数两种运行方式
- **网页模式**：视频与音频使用两个独立输入区，支持合集选择、取消、重试与重新下载，并实时显示任务状态、下载速度和预计剩余时间
- 单个链接下载失败时继续处理后续任务
- 错误使用稳定错误码和可执行建议；脱敏 JSONL 日志自动轮转
- 支持通用或平台专用 Cookie 文件
- 下载完成后显示成功、失败及文件路径汇总

## 目录结构

```text
Multiple_Video_Downloader/
├── main.py                      # 命令行入口
├── app.py                       # Web 服务入口
├── downloader.py                # 通用下载核心逻辑（main.py 与 app.py 共用）
├── bilibili_acceleration.py     # Bilibili CDN 测速、缓存与极速模式策略
├── collection_resolver.py       # 播放列表、合集与分 P 预览/选择
├── task_control.py              # Web 队列、取消、重试与重新下载
├── download_errors.py           # 结构化错误码与用户建议
├── download_logging.py          # 脱敏 JSONL 轮转日志
├── templates/
│   └── index.html               # Web 前端页面
├── requirements.txt             # Python 依赖
├── README.md
├── cookies.txt                  # 可选：通用 Cookie
├── youtube_cookies.txt          # 可选：YouTube 专用 Cookie
├── instagram_cookies.txt        # 可选：Instagram 专用 Cookie
├── bilibili_cookies.txt         # 可选：Bilibili 专用 Cookie
├── downloads/                   # 首次下载时自动创建
└── logs/                        # 首次记录任务事件时自动创建
```

Cookie 文件均为可选文件，不配置时无需创建。平台专用 Cookie 的优先级高于 `cookies.txt`。

## 一、准备运行环境

需要安装：

- Python 3.9 或更高版本
- pip
- FFmpeg

先将本项目下载或克隆到本机，然后在终端中进入项目根目录。下面的路径只是示例，请替换为项目在你电脑上的实际位置。

macOS（Terminal）：

```bash
cd /path/to/Multiple_Video_Downloader
```

Windows（PowerShell）：

```powershell
cd "C:\path\to\Multiple_Video_Downloader"
```

> 路径中包含空格时，macOS 和 Windows 都应使用引号包住完整路径。

确认 Python 版本：

macOS：

```bash
python3 --version
python3 -m pip --version
```

Windows（PowerShell）：

```powershell
python --version
python -m pip --version
```

创建并启用虚拟环境：

macOS：

```bash
python3 -m venv venv
source venv/bin/activate
```

Windows PowerShell：

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

如果 Windows PowerShell 的执行策略不允许运行激活脚本，可以不激活虚拟环境，直接使用其中的 Python：

```powershell
.\venv\Scripts\python.exe -m pip --version
```

安装 Python 依赖：

macOS（已激活虚拟环境）：

```bash
python -m pip install -r requirements.txt
```

Windows PowerShell（无需激活虚拟环境）：

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

`requirements.txt` 会同时安装 yt-dlp 和 `mutagen`；后者用于把封面元数据写入 FLAC 文件。请通过依赖文件安装，不要只单独安装 yt-dlp。

后续示例默认虚拟环境已经启用，因此统一使用 `python`。如果 Windows PowerShell 未启用虚拟环境，请将示例开头的 `python` 替换为 `.\venv\Scripts\python.exe`，例如使用 `.\venv\Scripts\python.exe app.py` 启动网站。

## 二、安装 FFmpeg

FFmpeg 用于合并最高质量的视频流和音频流、封装 MP4，以及处理 MP3、FLAC、原始音轨封装、WAV 和封面。没有 FFmpeg 时部分音视频输出无法完成。

macOS：

```bash
brew install ffmpeg
ffmpeg -version
```

Ubuntu / Debian：

```bash
sudo apt update
sudo apt install ffmpeg
ffmpeg -version
```

Windows：

1. 从 [FFmpeg 下载页](https://ffmpeg.org/download.html)下载 Windows 版本。
2. 解压后将 `bin` 目录加入系统 `PATH`。
3. 重新打开 PowerShell 并运行 `ffmpeg -version` 验证安装。

无论使用哪个系统，只要终端能正常显示 `ffmpeg -version` 的输出，本项目就能找到 FFmpeg。

### 可选：安装 aria2c 极速模式

标准模式不需要 aria2c。macOS 用户如需启用 Bilibili“极速模式”，可安装：

```bash
brew install aria2
aria2c --version
```

未安装或 aria2c 运行失败时，程序会自动切换回标准模式；YouTube 和 Instagram 不使用该加速器。

---

## 三、命令行模式

### 方式 A：交互式批量输入

在项目目录并启用虚拟环境后运行（macOS 和 Windows 通用）：

```bash
python main.py
```

程序会先要求选择下载类型：直接回车或输入 `1` 下载视频，输入 `2` 下载音频。选择音频后，可继续选择 MP3 V0、源 FLAC、原始音频或 WAV PCM；随后逐行请求链接，YouTube、Instagram 与 Bilibili 链接可以交替输入。

可以直接粘贴平台生成的分享文案，每行仍表示一个任务。程序会自动忽略标题并提取其中的第一个 HTTP(S) 链接，例如：

```text
【【梗百科】不X你们X什么是啥梗？！】https://www.bilibili.com/video/BV1xRuu6fEeA?vd_source=c29bf1bb20fc12664dae270045332759
```

```text
链接 1（空行结束）: https://www.youtube.com/watch?v=xxxx
链接 2（空行结束）: https://www.instagram.com/reel/yyyy/
链接 3（空行结束）: https://www.bilibili.com/video/BV1GJ411x7h7
链接 4（空行结束）:
```

输入最后一个链接后，再按一次回车提交空行。若检测到播放列表、合集或分 P，程序会先显示有序条目；输入 `all`、`1,3-5` 等选择（最多 100 项），再检查任务并在 `开始下载？(Y/n):` 后直接按回车或输入 `y`。

### 方式 B：通过命令行一次传入多个链接

下载视频（默认行为）：

macOS：

```bash
python main.py \
  "https://www.youtube.com/watch?v=xxxx" \
  "https://www.instagram.com/reel/yyyy/" \
  "https://www.bilibili.com/video/BV1GJ411x7h7?p=2"
```

Windows PowerShell：

```powershell
python main.py `
  "https://www.youtube.com/watch?v=xxxx" `
  "https://www.instagram.com/reel/yyyy/" `
  "https://www.bilibili.com/video/BV1GJ411x7h7?p=2"
```

只下载最高可用音质并转换为 MP3：

macOS：

```bash
python main.py --audio \
  "https://www.youtube.com/watch?v=xxxx" \
  "https://www.instagram.com/reel/yyyy/" \
  "https://b23.tv/BV1GJ411x7h7"
```

Windows PowerShell：

```powershell
python main.py --audio `
  "https://www.youtube.com/watch?v=xxxx" `
  "https://www.instagram.com/reel/yyyy/" `
  "https://b23.tv/BV1GJ411x7h7"
```

请求保留源 FLAC（仅在源站确实提供 FLAC 时输出无损文件）：

```bash
python main.py --audio --flac "https://www.bilibili.com/video/BV1fsTM6CE9P"
```

如果该内容没有 FLAC 音轨，任务不会失败，而是显示“源站未提供 FLAC，已自动回退至 MP3 V0”并输出 MP3 V0。

使用统一的 `--audio-format` 参数选择四种音频输出：

```bash
python main.py --audio --audio-format mp3 "https://youtu.be/xxxx"
python main.py --audio --audio-format flac "https://www.bilibili.com/video/BV1fsTM6CE9P"
python main.py --audio --audio-format source "https://youtu.be/xxxx"
python main.py --audio --audio-format wav "https://youtu.be/xxxx"
```

`source` 保留 yt-dlp 选中源音轨的实际编码与扩展名；`wav` 解码为未压缩 PCM，文件通常明显更大，但不会让有损源恢复为无损音质。旧命令 `--audio --flac` 仍然兼容，等价于 `--audio --audio-format flac`。

下载播放列表、合集或 Bilibili 分 P 时，命令行参数模式必须明确指定条目：

```bash
# 下载前 5 项
python main.py --items 1-5 "https://www.youtube.com/playlist?list=xxxx"

# 下载全部可用项；超过 100 项时会拒绝并要求缩小范围
python main.py --audio --audio-format source --items all \
  "https://www.bilibili.com/video/BVxxxxxxxxxx"
```

为 Bilibili 视频启用可选极速模式：

```bash
python main.py --turbo "https://www.bilibili.com/video/BV1xRuu6fEeA"
```

为 Bilibili MP3 音频启用可选极速模式：

```bash
python main.py --audio --turbo "https://www.bilibili.com/video/BV1xRuu6fEeA"
```

命令行参数模式不再二次确认，会立即开始下载。合集未带 `--items` 时会停止并给出中文提示，避免意外下载整个列表。`--flac` 与 `--audio-format` 只能和 `--audio` 一起使用；`--audio`、`--audio-format`、`--items` 与 `--turbo` 建议放在 URL 前面。未带 `--turbo` 时始终使用标准模式。始终用引号包住链接，避免链接中的 `&` 等字符被终端解释。macOS 终端使用反斜杠 `\` 续行，Windows PowerShell 使用反引号 `` ` `` 续行；也可以将整条命令写在同一行。

### 查看下载结果

任务结束后，视频汇总会显示平台、标题、分辨率、文件大小和保存路径；音频汇总会显示实际输出格式、源编码/码率、是否发生 FLAC 回退、文件大小和保存路径。所有文件都保存在项目根目录下的 `downloads/` 目录：

```text
Multiple_Video_Downloader/
└── downloads/
```

若其中一个链接失败，程序仍会继续下载剩余链接，并在最终汇总中列出失败项。

---

## 四、网页模式

除了命令行外，你也可以通过本地浏览器界面操作。

### 启动 Web 服务

在项目目录并启用虚拟环境后运行（macOS 和 Windows 通用）：

```bash
python app.py
```

启动后会显示：

```text
========================================================
  🎬 Multiple_Video_Downloader — Web 模式
========================================================
  浏览器访问:  http://127.0.0.1:8233
  下载目录:    downloader.py 同级的 downloads/
  按 Ctrl+C 停止服务
========================================================
```

### 浏览器中访问

打开浏览器，访问 **http://127.0.0.1:8233**

### 网页操作流程

1. 下载视频时，在 **“最高画质视频”** 区块粘贴链接或分享文案；只需要音频时，在独立的 **“最高音质音频”** 区块操作。
2. 音频可选 **MP3 V0**、**源 FLAC**、**原始音频**或 **WAV PCM**。原始音频的扩展名取决于源流；WAV 文件较大且不会提升源音质；源站没有 FLAC 时会自动回退 MP3 V0。
3. 点击下载后，系统先读取输入。单条内容保持一键提交；播放列表、合集与分 P 会显示共享预览面板，可勾选条目、全选并查看计数，一次最多提交 100 项。
4. 视频卡片与音频卡片各有独立的 **“极速模式”** 开关。检测不到 aria2c 时，开关会禁用；该开关只用于 Bilibili。
5. 后端所有批次共用最多 3 个工作槽，其中 Bilibili 最多同时运行 2 项。超过上限的任务保持“等待中”，有空位后自动开始。
6. 下方任务列表会显示等待、下载、不可中断的极速下载、完成、失败和已取消状态，并显示下载速度、预计剩余时间、进度、输出规格及保存路径。
7. 失败任务显示稳定的 `error_code`、中文说明和建议；每次尝试可展开查看状态和时间。
8. 可取消等待中或标准下载任务；失败/取消后可重试，批次中可一次重试所有可重试失败项；完成后可重新下载并保留旧文件。
9. 每个输入区都有独立的 **“清空输入”**。下载文件保存在 `downloads/` 目录中。

### 取消、重试与重新下载

- **取消**：等待任务立即取消；正在运行的标准任务在下载器的下一个协作检查点停止，并清理本次新生成的临时文件。
- **aria2c 极速任务**：进入“不可中断”状态后不提供取消按钮，必须等待该任务完成；这是已确认的极速模式行为。
- **重试**：失败或取消任务重新进入同一队列，并保留每一次尝试记录。不可重试错误不会显示重试操作。
- **重新下载**：只针对已完成任务，生成新任务且不覆盖原文件；新文件使用 `(2)`、`(3)` 等递增后缀。
- **批次保留**：服务在内存中最多保留 100 个批次，重启 Web 服务后历史任务状态清空，但已经下载的文件不会被删除。

### 测试批量下载

可以用以下公开测试链接验证网页功能：

```text
https://www.youtube.com/watch?v=jNQXAC9IVRw
https://www.youtube.com/watch?v=BaW_jenozKc
```

将上面两个链接粘贴到视频或音频区块（一行一个），点击对应下载按钮，观察任务状态从“等待中”→“下载中”→“下载完成”的变化过程。

### 停止 Web 服务

在终端中按 `Ctrl+C` 即可停止 Flask 服务。

---

## 五、支持的链接

| 平台 | 类型 | 示例 |
|---|---|---|
| YouTube | 标准视频 | `https://www.youtube.com/watch?v=xxxx` |
| YouTube | 短链接 | `https://youtu.be/xxxx` |
| YouTube | Shorts | `https://www.youtube.com/shorts/xxxx` |
| YouTube | 直播或回放 | `https://www.youtube.com/live/xxxx` |
| YouTube | 嵌入视频 | `https://www.youtube.com/embed/xxxx` |
| YouTube Music | 视频 | `https://music.youtube.com/watch?v=xxxx` |
| YouTube | 播放列表 | `https://www.youtube.com/playlist?list=xxxx` |
| YouTube | 带列表参数的视频 | `https://www.youtube.com/watch?v=xxxx&list=yyyy` |
| Instagram | Reels | `https://www.instagram.com/reel/xxxx/` |
| Instagram | 视频帖子 | `https://www.instagram.com/p/xxxx/` |
| Instagram | IGTV | `https://www.instagram.com/tv/xxxx/` |
| Instagram | Stories | `https://www.instagram.com/stories/username/xxxx/` |
| Bilibili | BV 视频 | `https://www.bilibili.com/video/BV1GJ411x7h7` |
| Bilibili | av 视频 | `https://www.bilibili.com/video/av170001` |
| Bilibili | 移动端视频 | `https://m.bilibili.com/video/BV1GJ411x7h7` |
| Bilibili | 指定分 P | `https://www.bilibili.com/video/BV1GJ411x7h7?p=2` |
| Bilibili | 多分 P 视频 | `https://www.bilibili.com/video/BVxxxxxxxxxx` |
| Bilibili | 合集 / 列表 | `https://www.bilibili.com/list/...`、`/medialist/...` |
| Bilibili | UP 主合集 | `https://space.bilibili.com/123/lists/...` |
| Bilibili | 短链接 | `https://b23.tv/BV1GJ411x7h7` |

程序会预览并选择 YouTube 播放列表、Bilibili 多分 P、`list` / `medialist` 及 UP 主 `lists` 页面；能否展开仍取决于 yt-dlp、页面公开状态和当前 Cookie 权限。Instagram 多视频帖子可按提取器返回结果预览，图片条目会标记为不可下载。

当前不承诺支持需要额外业务接口、DRM 或特殊账号权限的 Bilibili 番剧批量页、稍后再看、私密收藏夹，以及平台未向 yt-dlp 暴露条目的页面。无法解析时会返回 `COLLECTION_EXTRACT_FAILED`，不会静默下载错误内容。无论来源有多少条，一次最多选择 100 项。

### 输出文件名与音质说明

- YouTube 视频和音频使用内容标题命名；Instagram 与 Bilibili 文件名继续附加内容 ID，基础形式分别如 `Video by author [ABC123].mp3`、`标题 [内容ID].mp4` 和 `标题 [内容ID].mp3`，避免同标题内容互相覆盖。
- 实际音频文件名会在扩展名前追加真实规格。例如，以约 1521 kbps 的源 FLAC 转换 MP3 时得到 `标题 [内容ID] [MP3 V0 · 源FLAC 1521kbps].mp3`；保留源文件时得到 `标题 [内容ID] [FLAC Lossless · 1521kbps].flac`。
- MP3 V0 会先选取源站可获取的最高质量音轨，再使用 FFmpeg 的最高 VBR 品质设置转换。即使输入是 Hi-Res FLAC，MP3 成品仍是有损音频，不能保留真正的无损数据。
- “源 FLAC”只在提取结果确实包含 FLAC 音轨时直接输出 FLAC；程序不会把 AAC、Opus 等有损源转码并伪装成 FLAC。没有 FLAC 时自动回退 MP3 V0。
- MP3 和 FLAC 会自动嵌入视频封面；原始 M4A 等支持封面的容器也会尝试嵌入。WebM 与 WAV 不支持当前封面写入流程，会正常输出无封面音频；源内容没有封面时所有格式都照常完成。

### Bilibili 下载加速策略

- 选中流的大小不超过 50 MiB，或无法确定大小时：不额外测速，沿用当前 10 MiB 原生 HTTP 分块。
- 选中流的大小大于 50 MiB 时：仅从 Bilibili 响应提供的 HTTPS CDN 主机中最多测试 4 个，每个主机读取 512 KiB 样本，再比较 4 MiB 与 10 MiB 分块的实际表现。
- 测速结果在内存中缓存 30 分钟；Web 服务或命令行进程重启后缓存清空。
- 程序不修改或猜测 CDN 域名，也不会绕过平台的权限、风控或限速机制。
- aria2c 不可用、执行失败，或选中的 CDN 返回 `HTTP 403` / `HTTP 412` 时，会自动切换回标准模式或原始 CDN 继续尝试。
- 实际速度仍取决于地区、网络路由、账号状态和 Bilibili 当前 CDN 负载，无法保证固定幅度的提升。

### 结构化错误码与日志

网页会显示稳定的错误码、中文说明和建议，例如 `AUTH_REQUIRED`、`NETWORK_TIMEOUT`、`RATE_LIMITED`、`FORMAT_UNAVAILABLE`、`COLLECTION_EXTRACT_FAILED`、`ARIA2_FAILED` 与 `POSTPROCESS_FAILED`。CLI 下载错误使用相同格式，便于区分凭证、网络、格式、合集解析和后处理问题。

任务事件写入 `logs/downloader.jsonl`，每行一个 JSON 对象。单个日志达到 10 MiB 后自动轮转，最多保留 5 个备份。日志仅记录任务阶段、平台、媒体/音频格式、速度模式、尝试次数、耗时与错误字段；URL 查询参数、Cookie、Authorization、Token 和密码会被脱敏。日志目录不可写时只显示一次警告，不会让下载任务失败。

排查问题时可以查看最近事件：

```bash
tail -n 50 logs/downloader.jsonl
```

不要将整个日志或 Cookie 文件公开上传；即使日志已自动脱敏，也应只分享解决问题所需的最小片段。

## 六、需要登录时配置 Cookie

公开内容通常可以直接下载。私密内容、年龄限制内容或平台要求登录的内容需要有效 Cookie，并且当前登录账号必须本来就有权访问该内容。本程序不会绕过访问权限。

### 安装可信的 Cookie 导出扩展

本项目推荐开源扩展 **Get cookies.txt LOCALLY**。请通过下面的官方页面安装，并核对扩展名称及 GitHub 仓库；不要安装名称相似的旧版 **Get cookies.txt** 或来源不明的同名扩展。

- Chrome / Edge：[Chrome Web Store 安装页面](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
- Firefox：[Mozilla Add-ons 安装页面](https://addons.mozilla.org/en-US/firefox/addon/get-cookies-txt-locally/)
- 源代码与隐私说明：[kairi003/Get-cookies.txt-LOCALLY](https://github.com/kairi003/Get-cookies.txt-LOCALLY)

#### Chrome / Edge 安装

1. 打开上面的 Chrome Web Store 页面。
2. Chrome 点击 **“添加至 Chrome”**；Edge 点击 **“获取”**，若浏览器提示允许来自其他应用商店的扩展，请先确认页面域名确实是 `chromewebstore.google.com` 再允许。
3. 在浏览器扩展菜单中固定 **Get cookies.txt LOCALLY**，方便在目标平台页面使用。

#### Firefox 安装

1. 打开上面的 Mozilla Add-ons 页面。
2. 点击 **“添加到 Firefox”**，阅读权限说明后确认安装。
3. 在扩展管理器中允许该扩展访问目标平台页面；否则它无法读取并导出当前站点 Cookie。

### 按平台导出 Cookie

YouTube、Instagram 和 Bilibili 分别执行一次以下步骤，不要把三个站点的 Cookie 混在同一个平台专用文件中：

1. 在浏览器中登录目标平台，并打开该平台的视频页面，确认当前账号能够正常播放目标内容。
2. 保持目标平台页面为当前标签页，打开 **Get cookies.txt LOCALLY**。
3. 选择 **Netscape** 格式，使用扩展的当前站点导出功能，仅导出当前平台域名的 Cookie。
4. 保存文件后，用纯文本编辑器打开并检查首行包含 `# Netscape HTTP Cookie File`。不要修改后续 Cookie 行。
5. 将文件移动到本项目根目录，与 `main.py` 同级，并按平台重命名：

| 当前登录平台 | 建议打开的页面 | 保存文件名 |
|---|---|---|
| YouTube | `https://www.youtube.com/` | `youtube_cookies.txt` |
| Instagram | `https://www.instagram.com/` | `instagram_cookies.txt` |
| Bilibili | `https://www.bilibili.com/` | `bilibili_cookies.txt` |

平台专用 Cookie 优先于通用 `cookies.txt`。建议使用上表中的独立文件名；只有确实需要一个通用回退文件时才使用 `cookies.txt`。

### 让新 Cookie 生效

- CLI：结束当前命令后重新运行 `python main.py`。
- Web：停止正在运行的服务，重新执行 `python app.py`，即重启 8233 Web 服务，然后刷新页面并重新提交任务。
- 如果仍然提示登录、`HTTP 403` 或 Bilibili `HTTP 412`，先确认浏览器中的登录状态仍有效，再重新导出对应平台 Cookie。Cookie 过期或账号退出后必须重新导出。

### Cookie 安全

Cookie 文件等同于登录凭证。不要上传、分享、截图或提交到 Git，也不要粘贴到聊天、Issue 或日志中。扩展只应从上述官方商店链接安装。若 Cookie 已泄露，应立即在对应平台退出其他会话或撤销登录状态，必要时修改密码，然后删除旧文件并重新导出。

## 七、浏览器扩展开发路线

当前仓库尚未包含浏览器扩展。若要把“当前页面一键加入下载队列”做成可发布扩展，需要完成以下工作：

1. **定义本地 API 契约**：为 `http://127.0.0.1:8233` 增加扩展专用健康检查、预览、提交和任务查询接口；保持现有结构化错误响应，并约定 API 版本。
2. **增加本机配对安全**：Web 服务首次生成短期配对码，扩展交换得到本地访问令牌；限制允许的 Origin、请求方法和字段，令牌存入扩展本地存储。扩展不读取、不上传项目 Cookie 文件。
3. **创建 Manifest V3 扩展**：实现 popup、后台 service worker 和右键菜单。popup 负责选择视频/音频、四种音频格式与极速模式；service worker 负责提取当前标签页 URL、调用本地 API、轮询状态及恢复中断的 UI。
4. **坚持最小权限**：优先使用 `activeTab`、`contextMenus`、`storage` 和 `notifications`；`host_permissions` 只允许 `http://127.0.0.1:8233/*`。若不用内容脚本即可获得当前页面 URL，就不要申请读取所有网站内容的权限。
5. **处理合集选择**：单条页面可直接提交；播放列表、合集或分 P 先调用预览 API。条目较少时在 popup 勾选，条目多时打开本地网站的选择面板，继续遵守 100 项上限。
6. **状态与通知**：显示服务未启动、待配对、排队、下载中、不可取消的 aria2c、完成和结构化错误状态；下载完成后可用系统通知提示，但不要把敏感 URL 放进通知文本。
7. **测试与打包**：为 URL 识别、配对、API 失败、service worker 重启和权限边界编写自动化测试；在 Chrome/Edge 手动验证后生成商店包、隐私说明、图标和版本更新流程。
8. **适配 Safari 与 Firefox**：Firefox 需要核对当前 MV3 service worker、权限和商店签名差异；Safari 需通过 Xcode 转换为 Safari Web Extension、配置 App 容器并单独签名/公证。两者应复用协议和业务逻辑，但保留各自构建入口。

建议先完成 Chrome/Edge MVP：当前标签页 → popup 选择 → 本地配对 → 预览/提交 → 状态通知。确认本地 API 和权限模型稳定后，再移植 Safari 与 Firefox。

## 八、常见问题

| 问题 | 处理方式 |
|---|---|
| 未检测到 FFmpeg | 按上文安装 FFmpeg，并重新打开终端验证 `ffmpeg -version` |
| `HTTP 403` 或要求登录 | 配置对应平台的 Cookie，确认浏览器中可正常打开链接 |
| `HTTP 429` | 请求过于频繁，暂停一段时间后再试 |
| Instagram Story 无法下载 | 确认 Story 尚未过期，且登录账号有访问权限 |
| Bilibili 画质受限、要求登录或会员 | 确认账号本来有权播放该内容，再导出完整 Cookie 保存为 `bilibili_cookies.txt` |
| Bilibili 风控或 `HTTP 412` | 降低请求频率，切换到可正常访问 Bilibili 的网络环境后稍后重试；登录内容同时配置 `bilibili_cookies.txt` |
| Bilibili 下载速度较慢 | 项目使用 10 MB HTTP 分块，并且最多同时运行 2 个 Bilibili 下载任务；实际速度仍取决于 Bilibili 分配的 CDN 和网络路由，客户端优化不保证绕过平台侧限速 |
| 视频不可用或 404 | 在浏览器中确认链接仍有效且内容未被删除 |
| 网络连接超时 | 检查本机网络、代理或 VPN 配置后重试 |
| 下载后没有声音或无法合并 | 确认 FFmpeg 已安装并位于系统 `PATH` 中 |
| MP3 下载失败或提示没有音频流 | 确认 FFmpeg 可用；再在浏览器中确认源内容确实包含可播放的音频 |
| yt-dlp 突然无法解析平台 | 在虚拟环境中运行 `python -m pip install -U yt-dlp` 后重试 |
| Web 页面打不开 | 确认 `python app.py` 已启动且终端无报错，访问 `http://127.0.0.1:8233` |
| Web 进度出现控制码或乱码 | 重启 Web 服务并强制刷新页面；新版会在后端清除 yt-dlp 的终端颜色控制码 |
| Web 端口被占用 | 修改 `app.py` 中的 `WEB_PORT = 8233` 后重新启动服务 |

## 九、退出状态（命令行模式）

- 所有任务成功：退出码 `0`
- 任一任务失败或没有合法链接：退出码 `1`
- 用户通过快捷键取消交互：退出码 `130`

## 合规说明

本工具仅供学习及下载用户本人拥有权利、已获授权或平台允许下载的视频或音频内容。请遵守 YouTube、Instagram、Bilibili 的服务条款及所在地法律法规。不得使用本工具绕过 DRM、访问控制或下载无权使用的受版权保护内容。
