# Hero 花体标题设计

## 目标

将首页 Hero 主标题 `Capture. Convert. Keep.` 改为优雅的花体字，在取消粗体的同时保持现有字号和视觉中心地位。

## 字体方案

采用无需新增字体文件的系统花体字体栈：

```css
font-family: "Snell Roundhand", "Brush Script MT", "Segoe Script", cursive;
```

- macOS 优先使用 `Snell Roundhand`。
- 其他系统依次回退到 `Brush Script MT`、`Segoe Script` 和通用 `cursive`。
- 不引入网络字体、第三方依赖或字体授权文件。

## 样式规则

- 将主标题字重从 `650` 改为正常字重 `400`。
- 保留桌面字号 `clamp(48px, 8vw, 102px)`。
- 保留移动端字号 `clamp(44px, 15vw, 64px)`。
- 保留主标题最大宽度、Hero 布局、Reveal 动效和文案内容。
- 将原本适合无衬线粗体的紧缩字距调整为适合花体的轻微自然字距，避免笔画重叠。

## 验收

- 自动测试验证主标题使用完整花体字体栈和 `font-weight: 400`。
- 自动测试验证桌面与移动端字号规则保持不变。
- `Capture. Convert. Keep.` 文案及现有下载功能保持不变。
- 完整测试套件、编译检查及差异检查继续通过。
