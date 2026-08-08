# Bilibili 视频与音频下载支持设计

## 目标

在保留现有 YouTube、Instagram 下载行为的基础上，为 Web 与命令行入口增加 Bilibili 单视频页面和短链接支持。Bilibili 链接可以与现有平台链接混合进入同一批次，并同时支持最高可用质量的视频下载和最高可用音质的 MP3 下载。

## 产品边界

- 支持 Bilibili 普通单视频页面，包括 `BV`、`av`、桌面端和移动端视频链接。
- 支持 `b23.tv` 短链接，由 yt-dlp 解析其跳转目标。
- 分 P 链接只下载 `?p=` 指定的分 P；未指定 `p` 时下载第 1 P。
- 不展开或下载合集、收藏夹、播放列表、番剧、空间主页和推荐视频。
- 不下载弹幕、字幕、封面或其他附属资源。
- Web 保留现有独立的视频与音频输入区，不新增 Bilibili 专用输入框。
- CLI 与 Web 都允许在同一批次混合输入 YouTube、Instagram 和 Bilibili 链接。
- 继续使用最多 3 个并发任务、输入顺序结果和单任务失败隔离。

## 架构与数据流

`downloader.py` 继续作为 CLI 和 Web 的共享下载核心。增加 `BILIBILI = "bilibili"` 平台标识和对应平台名称，不改变现有 `(platform, normalized_url)` 任务结构、下载结果结构或进度事件协议。

`detect_platform()` 接受以下 Bilibili 链接：

- `bilibili.com/video/BV...`
- `bilibili.com/video/av...`
- `www.bilibili.com/video/...`
- `m.bilibili.com/video/...`
- `b23.tv/...`

平台检测只接受上述视频入口。空间、收藏夹、合集和番剧等其他路径返回不支持，以维持“一条链接对应一个下载任务”的现有边界。

`make_task()` 将合法 Bilibili 链接标准化并放入现有混合队列。`download_tasks()`、Web 批次状态和 CLI 汇总不增加平台特例，仅通过现有平台字段展示 `Bilibili`。

## 下载参数与输出

Bilibili 视频模式使用 yt-dlp 的最高可用视频流与最高可用音频流组合，并由 FFmpeg 合并为 MP4；如果只有单一媒体流，则使用最高可用的兼容回退。音频模式继续使用 `bestaudio/best`，并通过 `FFmpegExtractAudio` 以最高 VBR 品质输出 MP3。

所有 Bilibili 下载均保持 `noplaylist=True`，从而只处理链接当前指定的分 P。输出文件名使用标题并追加内容 ID，以降低同名视频或分 P 之间的覆盖风险：

- 视频：`标题 [内容ID].mp4`
- 音频：`标题 [内容ID].mp3`

现有 YouTube 和 Instagram 的选择器、文件名及后处理配置保持不变。

## Cookie 与访问权限

Cookie 查找沿用平台专用文件优先的规则：

1. `bilibili_cookies.txt`
2. `cookies.txt`

没有 Cookie 时下载游客权限下可获取的最高版本；存在 Cookie 时下载当前账号有权访问的最高版本。项目不会绕过登录、会员、地区或版权限制。

## Web 与命令行交互

Web 页面结构不变，只将支持平台的说明文字从 YouTube、Instagram 扩展为 YouTube、Instagram、Bilibili。视频与 MP3 音频仍使用各自独立输入框，并继续共用一个任务队列和活动批次限制。

CLI 的交互提示、非法链接提示、无有效参数提示和启动说明同步加入 Bilibili。现有命令保持兼容：

- `python main.py URL...` 下载视频。
- `python main.py --audio URL...` 下载 MP3 音频。

## 错误处理

- 登录或会员权限不足时，提示确认浏览器账号能访问该内容，并导出 `bilibili_cookies.txt`。
- 已删除、地区限制、版权限制、HTTP 403、HTTP 429 和无可用音轨沿用或扩展现有中文错误提示。
- FFmpeg 缺失时继续明确说明视频合并与 MP3 转换需要 FFmpeg。
- 单个 Bilibili 任务失败只将该任务标记为失败，不中断同批次中的其他平台任务。

## 文档更新

`README.md` 同步更新项目简介、目录结构、混合输入示例、支持链接表、Cookie 文件名、故障排查和合规说明。文档明确说明分 P 的单项行为与不支持自动展开的内容类型。

## 测试与验收

- URL 单元测试覆盖 `BV`、`av`、桌面端、移动端、带 `?p=` 的分 P 和 `b23.tv`。
- URL 单元测试拒绝 Bilibili 空间、收藏夹、合集和番剧链接。
- 下载选项测试覆盖 Bilibili 视频最高质量合并、音频最高质量 MP3、`noplaylist=True` 和内容 ID 文件名。
- Cookie 测试覆盖 `bilibili_cookies.txt` 优先于通用 `cookies.txt`。
- CLI 测试覆盖 Bilibili 文案与混合平台任务。
- Flask 与模板测试覆盖 API 接受 Bilibili 链接、批次平台名称和前端支持平台文案。
- 运行完整单元测试、Python `compileall`、模板 JavaScript 语法检查和 `git diff --check`。
- 使用 Flask 测试客户端验证视频与音频批次状态流。
- 网络条件允许时，对公开 Bilibili 单视频与 `b23.tv` 短链接各执行一次只读取元数据的冒烟验证，不下载媒体文件。

## 验收标准

用户可以从 Web 或 CLI 提交合法 Bilibili 单视频链接，在视频模式获得最高可用质量的 MP4，在音频模式获得最高可用音质来源转换的 MP3；链接可与 YouTube、Instagram 混合排队，现有平台行为和最多 3 并发限制不回归。
