## Ai4PDF v1.0.0 · PDF_AI助手

首个公开发布版本。把 PDF 原文、逐段双语翻译、阅读批注和自定义 AI 问答放在一个本地工作台中。

### 下载哪个文件？

| 文件 | 适合谁 |
| --- | --- |
| [Windows 安装包](https://github.com/Teslajia/Ai4PDF/releases/download/v1.0.0/Ai4PDF-1.0.0-windows-x64-setup.exe) | 推荐；双击安装，支持 Windows 10 / 11 x64 |
| [免安装 ZIP](https://github.com/Teslajia/Ai4PDF/releases/download/v1.0.0/Ai4PDF-1.0.0-windows-x64-portable.zip) | 完整解压后运行 `Ai4PDF.exe` |
| [Ai4PDF 源码](https://github.com/Teslajia/Ai4PDF/releases/download/v1.0.0/Ai4PDF-1.0.0-source.zip) | 开发者及开源再分发；普通使用无需下载 |

无需另外安装 Python 或 Node.js。安装时可选择文档库文件夹，启动后在浏览器打开 `http://127.0.0.1:8765/`。AI 功能需自行配置 API 地址、模型和 Key。

### 本版本功能

- 下载 `windows-x64-setup.exe` 双击安装，支持 Windows 10 / 11，无需 Python 或 Node.js。
- 提供桌面快捷方式、托盘打开/退出菜单，自动在浏览器打开本地阅读界面。
- PDF 原文、双语段落翻译、划线批注、文档库分类，以及自定义 API 科研助手。
- 安装时可选择本地文档库文件夹，也可接入已有 Ai4PDF 文档库；默认 `%LOCALAPPDATA%\Ai4PDF\data`。升级保留原库位置，卸载保留个人数据。
- AI 功能需要自行配置 API；安装包不包含作者的 API Key 或文档。

### 数据与升级

已有资料的文档库在升级时保持原位置。若需要迁移，请通过应用内设置操作；卸载保留文档及位置配置。关闭网页不会停止后台服务，退出请使用托盘菜单。

### 已知限制

当前没有内置 OCR，也不导出重新排版的双语 PDF。可导出带原文批注的 PDF 与双语 Markdown。复杂版面可能需要手动调整，AI 回答与行内公式请结合原文核实。

当前安装包未进行代码签名，Windows 可能提示未知发布者。由维护者确认来源和校验值后再使用。

### 校验与开源

下载 `SHA256SUMS.txt` 后，可执行 `Get-FileHash .\Ai4PDF-1.0.0-windows-x64-setup.exe -Algorithm SHA256` 与清单核对。Release 同时附上 Ai4PDF、PyMuPDF 和 MuPDF 的对应源码及第三方声明；后两项无需用于普通安装。

许可：AGPL-3.0。[项目介绍](https://github.com/Teslajia/Ai4PDF) · [使用指南](https://github.com/Teslajia/Ai4PDF/blob/v1.0.0/docs/USAGE.zh-CN.md) · [构建与迁移说明](https://github.com/Teslajia/Ai4PDF/blob/v1.0.0/RELEASE.md)

**English:** Download the Windows x64 installer, or extract the portable ZIP and run `Ai4PDF.exe`. No Python/Node.js setup is required. Bring your own Chat Completions API for AI features. Documents remain local and survive uninstall; AI requests send relevant text/images to your configured provider. No built-in OCR or bilingual PDF export is included. See the [English README](https://github.com/Teslajia/Ai4PDF/blob/v1.0.0/README.en.md).
