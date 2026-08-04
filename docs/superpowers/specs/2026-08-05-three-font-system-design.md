# 三字体排版系统设计

## 目标

将页面字体明确分为三个角色：Hero 主标题使用 `Cormorant Garamond Italic`，左上角 `MARK YANG` 单独使用 `Allura`，其余界面文字使用 `Manrope`。

## 字体加载

- 使用 Google Fonts CSS2 官方样式入口一次加载 Allura 400、Cormorant Garamond 400 Italic，以及 Manrope 400/500/600/700。
- 使用 `display=swap`，字体加载期间立即显示系统回退字体。
- 不提交字体二进制文件。
- Manrope 不包含中文字形；中文继续回退到 `-apple-system`、`Noto Sans SC` 等系统字体，避免缺字。

## 字体映射

- `.hero h1`：`"Cormorant Garamond", Georgia, serif`，`font-style: italic`，`font-weight: 400`，字号和布局不变。
- `.brand`：恢复为 Manrope；仅 `.brand-mark` 使用 `"Allura", cursive`，正常字重，字号继承不变。
- 其余正文、按钮、标签、指标、输入和任务文字统一使用 Manrope 优先的 UI 字体变量。
- `.hero-kicker` 移除旧花体覆盖，回到共享的 Manrope 标签规则。

## 保持不变

- 所有文字内容、字号、颜色、边框、间距、响应式规则和动效。
- 下载接口、任务逻辑、后端与端口配置。

## 验收

- 自动测试验证 Google Fonts 链接包含三个字体族及所需字重/斜体。
- 自动测试验证三种字体的选择器作用范围。
- 自动测试验证主标题桌面与移动端字号保持不变。
- 完整测试、编译、JavaScript 语法及差异检查通过。
