# 架构与安全重构

[English](ARCHITECTURE.md) · **简体中文** · [README](../README.zh-CN.md)

GTD 保留 Flask / Jinja 与原生 JavaScript 界面。Web 和 CLI 共用 yt-dlp / FFmpeg 下载核心；以下边界用于分离决策与执行，不引入额外框架或运行时依赖。

| 边界 | 职责 |
| --- | --- |
| `app.py` | Flask 应用工厂、HTTP 响应与路由协调 |
| `download_requests.py` | 校验提交、处理显式预览选择、规范化直链、保留被拒绝输入的序号 |
| `web_runtime.py` | 管理每个应用独立的任务管理器、预览和上传存储 |
| `download_options.py` | 根据不可变偏好配置和当前辅助函数集合构建 yt-dlp 选项 |
| `bilibili_recovery.py` | 规划尝试顺序，仅在可恢复失败后逐个加入备用主机 |
| `downloader.py` | 协调网络 I/O、取消、专属临时目录、字幕和最终输出 |
| `task_models.py` | 使用兼容 Python 3.10 的静态类型描述任务、尝试、进度、结果和批次 |
| `task_control.py` / `task_history.py` | 调度与状态保护 / 按白名单持久化历史 |
| `static/js/task_api.js` | 共享 JSON 请求超时和具有上限的指数退避计算 |

## Web 应用生命周期

`create_app(config=None, *, manager=None, uploads=None)` 创建拥有独立路由和生命周期信息的 Flask 应用。创建应用或 `import app` 时，不打开任务历史、不创建执行资源，也不清理过期上传。首次使用运行时资源时，通过应用独立的锁初始化一次。执行 `python app.py` 时会在服务启动前显式初始化并恢复历史任务。

默认的 `app.app` WSGI 对象和已有 Flask 端点名称保持可用。兼容代理 `task_manager`、`preview_store`、`upload_store` 在请求内解析到当前应用，在上下文外解析到默认应用。工作线程捕获所属应用的上传存储，不依赖 Flask 请求上下文。

测试或嵌入调用可使用独立路径：

```python
from app import create_app
from web_runtime import get_runtime

application = create_app({
    "TESTING": True,
    "GTD_HISTORY_PATH": "/tmp/gtd-example/tasks.sqlite3",
    "GTD_UPLOAD_ROOT": "/tmp/gtd-example/uploads",
})
runtime = get_runtime(application)
try:
    response = application.test_client().get("/api/batches")
    assert response.status_code == 200
finally:
    runtime.task_manager.shutdown()
```

初始化后由调用方负责关闭任务管理器，不应在单次 HTTP 请求结束时关闭。注入的管理器始终归调用方所有，包括运行时初始化失败的情况。路径可通过工厂配置或环境变量指定；默认仍为 `state/tasks.sqlite3` 和 `state/audio_uploads/`。

每个已初始化应用拥有进程内队列。标准单应用服务保持总计 3 个工作槽、Bilibili 2 个、Instagram 1 个。多个应用或服务进程不会共用调度器。

## 兼容性与资源归属

- 请求解析保持校验顺序、结构化错误、状态码、选择顺序及被拒绝直链的序号。HTTP 适配层负责序列化；解析器不依赖 Flask 请求状态。
- `_build_ydl_options(...)` 保持原签名，每次调用将当前辅助函数装入 `OptionsHooks`，保留测试替换点和能力发现行为。`DownloadPreferences` 收拢媒体、音频格式与速度偏好；编码和容器决策仍由现有音频输出配置负责。
- Bilibili 恢复模块只处理元数据和计划。取消检查、临时目录创建与清理、网络操作、字幕封装和输出收尾仍由下载器负责。Turbo 到标准模式、原 CDN 回退、备用顺序及复制与对象身份行为保持一致。
- 任务类型描述数据契约，不是运行时校验器或数据库迁移。SQLite 白名单继续排除内部执行能力与私有诊断。状态修改仍受原有锁和执行代次检查保护。
- 浏览器页面共享传输与退避计算，各自保留批次选择保护、轮询启停、渲染和语言处理。上传继续通过 XHR 提供进度与取消。JSON 超时覆盖响应正文读取；调用方决定是否解析 HTTP 错误正文。

## 验证方式

先运行变更边界的专项回归，再执行 README 中的完整 Python / JavaScript 与浏览器测试。优先从被提取函数的上一层验证外部行为，而不是只检查函数结构。

关键契约包括多平台选项、CDN 回退顺序、取消与临时目录归属、文件名防冲突、重启恢复、过期浏览器响应，以及读取正文时的请求超时。媒体集成测试使用生成的本地样本和真实 FFmpeg；源 FLAC 测试同时核对编码音频哈希、编码和元数据。平台下载测试模拟上游响应，测试通过不代表实时连通性或下载速度。
