# Bilibili 原生下载加速设计

## 目标

在不影响 YouTube、Instagram 下载策略，也不牺牲现有 Web 实时速度、进度和 ETA 展示的前提下，提高 Bilibili 直接 HTTPS 媒体流在单连接受限场景下的下载吞吐量。

## 已确认现状

- 当前 Bilibili 最高质量视频由 `bestvideo+bestaudio/best` 选择视频流和音频流，再合并为 MP4。
- 项目最多同时执行 3 个下载任务，但没有限制同时运行的 Bilibili 任务数。
- 实测样本 `https://b23.tv/hkl7PC7` 的视频流和音频流均为 `upos-hz-mirrorakam.akamaized.net` 上的直接 HTTPS 文件，没有可供 `concurrent_fragment_downloads` 并行处理的分片列表。
- yt-dlp 标准 aria2c 外部下载器只在文件完成后触发完成进度钩子，无法保持当前 Web 页面下载期间的实时百分比、速度和 ETA。

## 方案

### Bilibili 专用原生参数

只在 `platform == BILIBILI` 时向 yt-dlp 选项加入：

- `http_chunk_size = 10 * 1024 * 1024`，让原生 HTTP 下载器按 10 MB 范围请求媒体文件。
- `throttled_rate = 256 * 1024`，当速度低于 256 KiB/s 时让 yt-dlp 判断当前媒体地址可能受限并重新提取。

YouTube 和 Instagram 的选项保持不变。已有 cookies、最高质量格式、文件名、重试和后处理逻辑保持不变。

### Bilibili 并发边界

保留全局 `MAX_PARALLEL_DOWNLOADS = 3`，并新增 `MAX_PARALLEL_BILIBILI_DOWNLOADS = 2`。

`download_tasks()` 继续使用最多 3 个线程处理混合平台任务，同时使用一个 Bilibili 专用的有界信号量，确保任意时刻最多只有 2 个 Bilibili 任务进入 `download_video()`。因此：

- 3 个 Bilibili 任务最多同时运行 2 个。
- 2 个 Bilibili 加 1 个 YouTube 或 Instagram 仍可同时运行，总任务数不超过 3。
- 返回结果顺序、异常隔离和进度事件索引保持不变。

### 实时进度

继续使用 yt-dlp 原生下载器和现有 `progress_hooks`。前端不增加新控件，不改变任务卡片结构，速度、百分比和 ETA 继续通过现有回调更新。

## 测试设计

### 自动化测试

- 验证 Bilibili 视频和音频选项都包含 10 MB `http_chunk_size` 与 256 KiB/s `throttled_rate`。
- 验证 YouTube 和 Instagram 选项不包含上述 Bilibili 专用参数。
- 验证三个 Bilibili 任务的实际并发数不超过 2，且结果顺序不变。
- 验证混合任务仍能达到全局 3 个并发，并保持 Bilibili 子上限 2。
- 运行完整单元测试、Python 编译、前端 JavaScript 语法检查和 `git diff --check`。

### 受控测速

使用同一个 Bilibili 链接、相同 cookies、相同网络、相同最高质量格式，分别记录基线与优化版本的媒体下载阶段：

- 平均下载速度；
- 峰值下载速度；
- 完成相同字节数所需时间；
- 是否出现 HTTP 403、412、重试或进度回退。

测速一次只运行一个 Bilibili 任务，避免任务间带宽竞争。若样本文件过大，使用相同时间窗口或相同字节上限进行对照，不将 FFmpeg 合并时间计入网络吞吐量。

## 成功与回退标准

- 自动化测试全部通过，现有 Web 实时进度没有回归。
- 优化版本在同条件下的平均吞吐量高于基线，且没有新增 HTTP 403、412 或连续重新提取。
- 如果 10 MB 分块没有改善，或触发重复重新提取、明显速度波动或平台风控，则不保留无效参数；保留已验证安全的并发限制，并报告瓶颈属于 CDN 路由而非客户端分块策略。
- 本阶段不安装或默认启用 aria2c，也不实现自定义 CDN 改写或自定义多连接下载器。

## 文档

README 的性能说明将明确：Bilibili 实际速度取决于平台分配的 CDN 和当前网络路由；项目使用保守的原生分块与最多 2 个 Bilibili 并发任务，不保证绕过平台侧限速。
