# 分享文案 URL 提取设计

## 目标

允许 Web、CLI 和 Web API 直接接收包含标题或其他说明文字的平台分享文案，从中提取有效视频 URL，再复用现有 YouTube、Instagram、Bilibili 平台校验与下载流程。

典型 Bilibili 输入：

```text
【【梗百科】不X你们X什么是啥梗？！】https://www.bilibili.com/video/BV1xRuu6fEeA?vd_source=c29bf1bb20fc12664dae270045332759
```

规范化结果：

```text
https://www.bilibili.com/video/BV1xRuu6fEeA?vd_source=c29bf1bb20fc12664dae270045332759
```

## 解析边界

- 在每条输入中查找第一个以 `http://` 或 `https://` 开头的 URL。
- URL 在空白字符处结束。
- 删除 URL 末尾不属于链接的常见中英文包围符号和句末标点，例如 `】）》」』〕〉`、逗号、句号、问号、感叹号和分号。
- 保留 URL 查询参数，包括 Bilibili 的 `?vd_source=...` 和 `?p=...`。
- 完整的纯 URL 输入保持现有行为。
- 不带协议的纯域名输入继续由现有逻辑补全 `https://`。
- 如果整条输入没有 HTTP(S) URL，则按现有规则处理，不从普通标题文字中猜测链接。

## 架构与数据流

解析逻辑放在 `downloader.py::normalize_url()`，使 `detect_platform()`、`make_task()`、CLI 和 Web API 自动共享同一行为，不在前端或 Bilibili 分支中增加重复实现。

`normalize_url()` 只负责提取和清理候选 URL。提取结果仍必须通过 `detect_platform()` 的平台域名与视频路径校验，因此分享文案不会放宽现有安全边界，也不会让空间主页、合集、番剧或其他非视频 URL 进入任务队列。

前端继续按“一行一个任务”提交输入。每一行可为纯 URL 或含一个 URL 的分享文案；本功能不将同一行中的多个链接拆成多个任务。

## 兼容性

- Bilibili `BV`、`av`、移动端、分 P 和 `b23.tv` 行为保持不变。
- YouTube 和 Instagram 纯 URL 行为保持不变。
- 因解析位于共享核心，含标题的 YouTube 或 Instagram 分享文案也可以提取首个 HTTP(S) URL。
- 下载格式、Cookie、文件名、并发限制、进度事件与 Web 页面结构均不改变。

## 错误处理

- 分享文案中没有 URL 时，继续显示现有“不支持的链接”提示。
- 提取出的 URL 不属于受支持平台或不是受支持的视频路径时，继续拒绝该输入。
- URL 后存在中文结束标点时，标点不进入 yt-dlp 请求。

## 文档与界面

Web 输入框提示更新为可粘贴“链接或平台分享文案”，但不新增输入框或控件。

`README.md` 增加 Bilibili 分享文案示例，说明程序会自动忽略标题并提取 URL，同时继续保持每行一个任务。

## 测试与验收

- 单元测试覆盖用户提供的完整 Bilibili 分享文案，并断言保留 `vd_source` 查询参数。
- 单元测试覆盖 URL 后带中文右括号或句末标点的情况。
- 单元测试覆盖含 YouTube/Instagram URL 的分享文案，证明行为位于共享核心。
- 单元测试覆盖无 URL 文本和非视频 URL，确认仍被拒绝。
- Web API 测试覆盖分享文案被规范化为干净 URL 后写入批次。
- 模板与 README 测试覆盖新的输入提示和操作说明。
- 运行完整单元测试、Python `compileall`、前端 JavaScript 语法检查和 `git diff --check`。
- 重启 8233 服务并确认页面实际包含新的分享文案提示。

## 验收标准

用户可以直接把包含标题和 Bilibili 视频 URL 的整行分享文本粘贴到视频或音频输入区，项目只将其中的有效 URL 写入下载任务，并保持所有现有平台校验与下载行为不回归。
