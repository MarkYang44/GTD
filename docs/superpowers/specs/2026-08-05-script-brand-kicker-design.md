# 品牌栏与 Hero 标签花体设计

## 目标

让首页的 `MARK YANG / DOWNLOADER` 与 `YOUTUBE + INSTAGRAM / ONLINE` 使用和 Hero 主标题相同风格的系统花体，同时保持它们现有的视觉层级、字号和位置。

## 字体规则

两处文字使用与主标题一致的字体栈：

```css
font-family: "Snell Roundhand", "Brush Script MT", "Segoe Script", cursive;
```

- 字重统一改为 `400`，不使用粗体。
- 保留现有大写文案，不改变文本内容。
- 调整为适合花体大写字母的紧凑字距，避免原等宽字体字距导致文字过散。

## 作用范围

- `.brand`：覆盖 `MARK YANG` 与 `/ DOWNLOADER` 整行。
- `.hero-kicker`：单独覆盖 `YOUTUBE + INSTAGRAM / ONLINE`。
- `.hero-kicker` 虽与 `.section-index`、`.card-index`、`.metric-label` 共用基础规则，但花体覆盖仅写在独立的 `.hero-kicker` 规则内。
- 不改变其他技术标签、指标标签、下载卡片编号或任务区域字体。

## 保持不变

- `.brand` 桌面字号 `12px` 和移动端字号 `10px`。
- `.hero-kicker` 字号 `11px`。
- 品牌方框、颜色、间距、Hero 标签横线、布局和 Reveal 动效。
- 页面文案、下载功能、后端及第三方依赖。

## 验收

- 自动测试验证 `.brand` 和独立 `.hero-kicker` 均使用完整花体字体栈及 `font-weight: 400`。
- 自动测试验证品牌与 Hero 标签的现有字号保持不变。
- 自动测试验证 `.section-index`、`.card-index` 和 `.metric-label` 仍保留等宽字体基础规则。
- 完整测试、编译检查和差异检查继续通过。
