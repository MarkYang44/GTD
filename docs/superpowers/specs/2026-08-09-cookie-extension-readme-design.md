# Cookie 导出扩展安装说明设计

## 目标

在项目 `README.md` 的 Cookie 配置章节中，提供一套可直接操作的浏览器扩展安装与 Cookie 导出流程，使用户能够为 YouTube、Instagram 和 Bilibili 生成项目可识别的 Netscape `cookies.txt` 文件。

## 采用方案

只推荐开源扩展 **Get cookies.txt LOCALLY**，并仅链接到以下可核验来源：

- Chrome / Edge：Chrome Web Store 官方扩展页面。
- Firefox：Mozilla Add-ons 官方扩展页面。
- 源代码与隐私说明：扩展作者的 GitHub 仓库。

不列出名称相似的旧版或第三方 Cookie 扩展，避免误装和来源混淆。README 将明确提醒用户核对扩展名称、作者仓库和商店链接。

## README 内容结构

在“需要登录时配置 Cookie”章节内扩展为以下内容：

1. 解释什么时候需要 Cookie，以及 Cookie 不会绕过账号本身没有的权限。
2. 分别说明 Chrome / Edge 与 Firefox 的扩展安装步骤。
3. 说明三个平台通用的导出流程：
   - 在浏览器中登录目标平台；
   - 打开该平台的网页并确认内容可播放；
   - 打开扩展，选择 Netscape 格式；
   - 只导出当前平台域名的 Cookie；
   - 将文件移动到项目根目录并按平台重命名。
4. 提供平台到文件名的精确映射：
   - YouTube → `youtube_cookies.txt`
   - Instagram → `instagram_cookies.txt`
   - Bilibili → `bilibili_cookies.txt`
   - `cookies.txt` 只作为通用回退文件。
5. 说明导出后的验证与生效方式：确认文件首行是 Netscape Cookie 文件标识，重启 CLI 命令或 8233 Web 服务，然后重新提交任务。
6. 增加安全警告：Cookie 等同于登录凭证，不上传、不截图、不提交 Git；若泄露，应退出平台会话、修改密码或撤销会话后重新导出。

## 边界

- 不修改 Cookie 查找逻辑、下载器参数或 Web 接口。
- 不安装浏览器扩展，也不读取现有 Cookie 文件。
- 不推荐浏览器开发者工具手工拼接 Cookie，因为步骤复杂且容易生成不兼容格式。
- 商店页面变化时，以扩展官方 GitHub 仓库提供的链接为准。

## 验证

扩展现有 README 文档测试，检查以下信息存在：扩展名称、Chrome / Edge 与 Firefox 官方链接、Netscape 格式、三个平台文件名、项目根目录、服务重启步骤和 Cookie 安全警告。随后运行相关文档测试、完整测试套件和 `git diff --check`。
