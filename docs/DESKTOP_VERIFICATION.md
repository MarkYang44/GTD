# GTD Desktop 验证记录

目标：macOS Apple Silicon 成品；Windows x64 源码及自动构建由用户在另一台电脑验证原生行为。

## 本机已验证

- 原项目单元/JavaScript 基线：479 项通过，2 项平台跳过。
- 最终单元及 JavaScript 回归：506 项通过，2 项平台跳过。
- 完整浏览器回归：32 项通过。初次完整运行暴露轮播 Home 导航与窗口缩放的竞态；已定位到平滑滚动中间页覆盖目标页，新增“返回期间缩放”的回归后修复，最终完整套件通过。
- 桌面专用回归：27 项通过，覆盖资源路径、会话请求防护、单实例锁、导入与构建资源清单。
- macOS 原生 QtWebEngine：10 个导航入口实际渲染；中英文/深浅主题同时反映在页面和原生侧栏。
- 原生文件夹窗口：人工通过桌面 UI 选择测试目录，下载位置输入框与提示均更新为所选目录。
- 原生视频选择器：选择生成的短 MP4，上传、提取原始 M4A 音轨成功；通过原生保存窗口另存，结果 5632 字节且与原始输出完全一致。
- 最终冻结成品复制到包含空格的独立目录，在 PATH=/usr/bin:/bin 下自检成功：9 个页面、FFmpeg/ffprobe/aria2/Node 各自运行，真实 MP4 上传 → MP3 提取 → 结果下载全部通过。运行工具均位于 .app 包内，没有使用系统媒体工具。
- 最终 .app 通过正常应用启动入口启动，初始中文界面、全部侧栏和内容可见，截图见 screenshots/gtd-desktop.png。
- 最终 macOS 成品深度/严格签名校验通过；为临时签名，不是 Apple Developer 签名或公证。
- 包含 111 项公开资源、媒体工具及必要运行库、许可证/来源说明。Cookie、日志、下载文件、任务数据库、人工导入草稿及备份未纳入打包资源清单。
- 最终冻结轮播脚本及桌面说明与源码逐字节相同。

## 成品

- `dist/GTD-darwin-arm64.zip`：476,996,668 字节。
- SHA256：`4a76dd1c6452f1aeef6a2a71816ca3ef8c9684722385c23bb0c525ba5651d9b1`。

## 复现命令

```sh
venv/bin/python -m unittest discover -s tests -p 'test_*.py'
PLAYWRIGHT_BROWSERS_PATH=/tmp/gtd-playwright venv/bin/python -m unittest discover -s tests/browser -p 'test_*.py'
.venv-desktop/bin/python tests/desktop_gui_smoke.py
.venv-desktop/bin/python scripts/build_desktop.py
GTD_DATA_DIR=/tmp/gtd-frozen-test PATH=/usr/bin:/bin dist/GTD.app/Contents/MacOS/GTD --self-test --report /tmp/gtd-frozen-test/report.json
codesign --verify --deep --strict dist/GTD.app
```

## 证据与边界

本轮日志：`/tmp/gtd-desktop-delivery-unit.log`、`/tmp/gtd-browser-gallery-fix.log`、`/tmp/gtd-desktop-build-delivery.log`、`/tmp/gtd-delivery-proof/report.json`、`/tmp/gtd-window-smoke.json`、`/tmp/gtd-preferences-smoke.json`。临时文件可能被系统清理；本文件保留验证结论与复现方式。

Windows 已实际在 GitHub Actions 构建成功（3a9d1cc；运行 37529896544）：EXE/CLI、9 个页面、包内 FFmpeg/ffprobe 9.0.2、aria2 1.37.0、Node 22.16.0，以及 MP4 上传→MP3 提取→结果下载均通过冻结自检。便携包 Artifact 为 GTD-windows-x64（11444710414）。这里没有运行 Windows 原生窗口，实体机验收由用户执行，步骤见 DESKTOP.md。也没有把各外站真实下载成功率或 Cookie 权限当成跨平台打包验证结论；网络下载仍复用原有执行器和已通过的相关回归。

源码上传目标：GitHub 的 codex/gtd-desktop 分支。macOS ZIP 不加入 Git 仓库；Windows 构建产物通过 Actions Artifact 获取，不自动发布 Release。

Windows 首次资源审计因反斜杠路径与默认字符集失败，已修复为统一 POSIX 清单路径和明确 UTF-8；修复后 Windows 构建成功。原测试矩阵另发现缺少 FFmpeg、Windows 环境大小写差异及测试清空 HOME 的假设，已补齐 CI 工具依赖并修正测试隔离；后续 CI 状态以 GitHub 为准。
