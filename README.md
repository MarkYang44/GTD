# YouTube + Instagram 视频与 MP3 音频批量下载工具

这是一个基于 [yt-dlp](https://github.com/yt-dlp/yt-dlp) 的程序，支持**命令行**和**网页**两种使用方式。它可以在同一批任务中自动识别 YouTube 和 Instagram 链接，既能下载视频，也能提取最高可用音质并转换为 MP3。最终文件统一保存到项目内的 `downloads/` 文件夹。

## 功能

- 一次输入多个 YouTube 与 Instagram 链接
- 一批任务最多同时处理 3 个链接，超过上限的任务自动排队
- 两个平台的链接可以任意混合，程序自动识别平台
- YouTube 自动选择可用的最高画质与最高音质
- 音频模式选择源站可获取的最高质量音轨，并转换为高质量 VBR MP3
- Instagram 支持 Reels、视频帖子、IGTV 和有效期内的 Stories
- 使用 FFmpeg 合并音视频并输出 MP4，或将音轨转换为 MP3
- **命令行模式**：交互式输入和命令行参数两种运行方式
- **网页模式**：视频与 MP3 音频使用两个独立输入区，实时显示每个任务的下载状态、下载速度和预计剩余时间
- 单个链接下载失败时继续处理后续任务
- 支持通用或平台专用 Cookie 文件
- 下载完成后显示成功、失败及文件路径汇总

## 目录结构

```text
Ytb_Ins_Video_Download/
├── main.py                      # 命令行入口
├── app.py                       # Web 服务入口
├── downloader.py                # 通用下载核心逻辑（main.py 与 app.py 共用）
├── templates/
│   └── index.html               # Web 前端页面
├── requirements.txt             # Python 依赖
├── README.md
├── cookies.txt                  # 可选：通用 Cookie
├── youtube_cookies.txt          # 可选：YouTube 专用 Cookie
├── instagram_cookies.txt        # 可选：Instagram 专用 Cookie
└── downloads/                   # 首次下载时自动创建
```

Cookie 文件均为可选文件，不配置时无需创建。平台专用 Cookie 的优先级高于 `cookies.txt`。

## 一、准备运行环境

需要安装：

- Python 3.9 或更高版本
- pip
- FFmpeg

进入项目目录：

```bash
cd /Users/markyang/Projects/Ytb_Ins_Video_Download
```

创建并启用虚拟环境：

```bash
python3 -m venv venv
source venv/bin/activate
```

Windows 使用：

```cmd
python -m venv venv
venv\Scripts\activate
```

安装 Python 依赖：

```bash
python -m pip install -r requirements.txt
```

## 二、安装 FFmpeg

FFmpeg 用于合并最高质量的视频流和音频流、封装 MP4，以及把最高可用质量的源音轨转换为 MP3。没有 FFmpeg 时无法完成 MP3 输出。

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
3. 重新打开终端并运行 `ffmpeg -version` 验证安装。

---

## 三、命令行模式

### 方式 A：交互式批量输入

在项目目录并启用虚拟环境后运行：

```bash
python main.py
```

程序会先要求选择下载类型：直接回车或输入 `1` 下载视频，输入 `2` 下载 MP3 音频。随后逐行请求链接，YouTube 与 Instagram 链接可以交替输入，例如：

```text
链接 1（空行结束）: https://www.youtube.com/watch?v=xxxx
链接 2（空行结束）: https://www.instagram.com/reel/yyyy/
链接 3（空行结束）: https://youtu.be/zzzz
链接 4（空行结束）:
```

输入最后一个链接后，再按一次回车提交空行。检查程序列出的平台与链接，然后在 `开始下载？(Y/n):` 后直接按回车或输入 `y`。

### 方式 B：通过命令行一次传入多个链接

下载视频（默认行为）：

```bash
python main.py \
  "https://www.youtube.com/watch?v=xxxx" \
  "https://www.instagram.com/reel/yyyy/" \
  "https://youtu.be/zzzz"
```

只下载最高可用音质并转换为 MP3：

```bash
python main.py --audio \
  "https://www.youtube.com/watch?v=xxxx" \
  "https://www.instagram.com/reel/yyyy/"
```

命令行参数模式不再二次询问，会立即开始下载。`--audio` 可放在 URL 参数之间，但建议放在最前面。始终用引号包住链接，避免链接中的 `&` 等字符被终端解释。

### 查看下载结果

任务结束后，视频汇总会显示平台、标题、分辨率、文件大小和保存路径；音频汇总会显示平台、标题、MP3 格式、音频编码、文件大小和保存路径。所有文件保存在：

```text
/Users/markyang/Projects/Ytb_Ins_Video_Download/downloads/
```

若其中一个链接失败，程序仍会继续下载剩余链接，并在最终汇总中列出失败项。

---

## 四、网页模式

除了命令行外，你也可以通过本地浏览器界面操作。

### 启动 Web 服务

在项目目录并启用虚拟环境后运行：

```bash
python app.py
```

启动后会显示：

```text
========================================================
  🎬 Ytb/Ins Downloader — Web 模式
========================================================
  浏览器访问:  http://127.0.0.1:8233
  下载目录:    downloader.py 同级的 downloads/
  按 Ctrl+C 停止服务
========================================================
```

### 浏览器中访问

打开浏览器，访问 **http://127.0.0.1:8233**

### 网页操作流程

1. 下载视频时，在上方 **“视频下载”** 区块粘贴 YouTube 或 Instagram 链接，**一行一个**，再点击 **“下载最高质量视频”**。
2. 只需要音频时，在下方独立的 **“MP3 音频下载”** 区块粘贴链接，再点击 **“下载最高音质 MP3”**。
3. 后端每批最多同时处理 3 个链接，超过上限的任务会保持“等待中”，直到有下载位置空闲。网页同一时间只运行一个批次；任一批次运行时，视频和音频两个输入区都会暂时禁用。
4. 下方任务列表会实时显示每个链接的状态：
   - **等待中** — 尚未开始下载
   - **下载中** — 当前正在下载（带闪烁动画），任务框内显示下载速度、预计剩余时间和进度百分比
   - **下载完成** — 视频显示标题、分辨率和文件大小；音频显示标题、MP3 格式、音频编码、文件大小和保存路径
   - **下载失败** — 下载失败，显示错误原因
5. 每个区块都有独立的 **“清空输入”**；下载期间不可清空，另一区块中尚未提交的内容会保留。
6. 所有任务完成后，两个区块恢复可用，可继续提交下一批链接。
7. 下载的文件保存在 `downloads/` 目录中。

### 测试批量下载

可以用以下公开测试链接验证网页功能：

```text
https://www.youtube.com/watch?v=jNQXAC9IVRw
https://www.youtube.com/watch?v=BaW_jenozKc
```

将上面两个链接粘贴到视频或 MP3 音频区块（一行一个），点击对应下载按钮，观察任务状态从“等待中”→“下载中”→“下载完成”的变化过程。

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
| Instagram | Reels | `https://www.instagram.com/reel/xxxx/` |
| Instagram | 视频帖子 | `https://www.instagram.com/p/xxxx/` |
| Instagram | IGTV | `https://www.instagram.com/tv/xxxx/` |
| Instagram | Stories | `https://www.instagram.com/stories/username/xxxx/` |

YouTube 播放列表链接不会整表下载；程序按单个视频处理。Instagram 图片帖子没有视频内容时无法生成视频文件。

### 输出文件名与音质说明

- YouTube 视频和音频使用内容标题命名，例如 `示例标题.mp4` 或 `示例标题.mp3`。
- Instagram 文件名附加内容 ID，例如 `Video by author [ABC123].mp3`，避免同标题内容互相覆盖。
- “最高音质”表示先选择源站当时可获取的最高质量音轨，再使用 yt-dlp/FFmpeg 的最高 VBR 品质设置转换为 MP3。MP3 是有损格式，转换不能提升源音轨本身的真实音质。

## 六、需要登录时配置 Cookie

公开内容通常可以直接下载。私密内容、年龄限制内容或平台要求登录的内容需要有效 Cookie，并且当前登录账号必须本来就有权访问该内容。本程序不会绕过访问权限。

操作步骤：

1. 在浏览器中正常登录对应平台。
2. 使用可信的浏览器扩展将 Cookie 导出为 Netscape 格式的 `cookies.txt`。
3. 将文件放到本项目根目录，与 `main.py` 同级。
4. 根据平台命名为 `youtube_cookies.txt` 或 `instagram_cookies.txt`；也可直接使用通用名称 `cookies.txt`。
5. 重新运行下载命令（命令行或网页模式均可，Cookie 由 `downloader.py` 自动加载）。

Cookie 属于敏感登录凭证，不要发送给他人，也不要提交到公开代码仓库。Cookie 失效后需要重新导出。

## 七、常见问题

| 问题 | 处理方式 |
|---|---|
| 未检测到 FFmpeg | 按上文安装 FFmpeg，并重新打开终端验证 `ffmpeg -version` |
| `HTTP 403` 或要求登录 | 配置对应平台的 Cookie，确认浏览器中可正常打开链接 |
| `HTTP 429` | 请求过于频繁，暂停一段时间后再试 |
| Instagram Story 无法下载 | 确认 Story 尚未过期，且登录账号有访问权限 |
| 视频不可用或 404 | 在浏览器中确认链接仍有效且内容未被删除 |
| 网络连接超时 | 检查本机网络、代理或 VPN 配置后重试 |
| 下载后没有声音或无法合并 | 确认 FFmpeg 已安装并位于系统 `PATH` 中 |
| MP3 下载失败或提示没有音频流 | 确认 FFmpeg 可用；再在浏览器中确认源内容确实包含可播放的音频 |
| yt-dlp 突然无法解析平台 | 在虚拟环境中运行 `python -m pip install -U yt-dlp` 后重试 |
| Web 页面打不开 | 确认 `python app.py` 已启动且终端无报错，访问 `http://127.0.0.1:8233` |
| Web 进度出现控制码或乱码 | 重启 Web 服务并强制刷新页面；新版会在后端清除 yt-dlp 的终端颜色控制码 |
| Web 端口被占用 | 修改 `app.py` 中的 `WEB_PORT = 8233` 后重新启动服务 |

## 八、退出状态（命令行模式）

- 所有任务成功：退出码 `0`
- 任一任务失败或没有合法链接：退出码 `1`
- 用户通过快捷键取消交互：退出码 `130`

## 合规说明

本工具仅供学习及下载用户本人拥有权利、已获授权或平台允许下载的视频或音频内容。请遵守 YouTube、Instagram 的服务条款及所在地法律法规。不得使用本工具绕过 DRM、访问控制或下载无权使用的受版权保护内容。
