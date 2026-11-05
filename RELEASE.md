# Windows 安装版与 GitHub Release

## 给使用者

- Windows 10 / 11，64 位（x64）。下载 `Ai4PDF-1.0.0-windows-x64-setup.exe`，双击安装，安装完成即可使用。
- 无需安装 Python、Node.js 或单独下载前端依赖。默认浏览器中运行阅读界面，本地服务只监听 `127.0.0.1`。
- 桌面及开始菜单提供 Ai4PDF 快捷方式。启动后自动打开界面，任务栏通知区域提供打开、日志、退出菜单。关闭网页不会停止服务；退出请使用托盘菜单。
- 安装默认无需管理员权限。安装向导分别提供「程序安装位置」和「本地文档库位置」：文档库可直接输入路径或点击「浏览」，例如 `D:\Ai4PDF Library`，支持中文及带空格的文件夹。可选空文件夹或已有的 Ai4PDF 文档库；普通 PDF 文件夹不会自动导入。安装完成后的首次启动立即使用所选位置。
- 程序默认位于 `%LOCALAPPDATA%\Programs\Ai4PDF`；文档库默认位于 `%LOCALAPPDATA%\Ai4PDF\data`，位置配置位于 `%LOCALAPPDATA%\Ai4PDF\library-location.json`。文档库不能放在程序安装目录内。取消安装不会保存库位置；升级、卸载保留个人数据及位置配置。
- 已有资料的重装/升级会显示并保留当前文档库，防止切到空库；若需迁移，请安装后使用「设置 → 文档库位置迁移」。若通过 `AI4PDF_DATA` 或 `PAPERDESK_DATA` 指定目录，安装向导显示该位置并保留环境变量配置。
- 便携 ZIP 解压后运行 `Ai4PDF.exe`，也无需环境安装。它同样使用上述用户数据目录，不把文档放在解压目录中。
- AI 问答和翻译仍需要在设置中填写自己的 API 地址、模型及 Key。PDF 阅读和批注无需 AI API。
- 首次发布的安装包尚无代码签名证书，Windows SmartScreen 可能提示未知发布者。请核对下载来源及 `SHA256SUMS.txt`。

## 现有源码版用户

先退出旧版命令行服务，避免占用 8765 端口。安装版不会自动寻找或改写其他目录中的文档库。

如需沿用原文档库：在旧版设置中查看实际文档库位置，退出旧版；首次安装时在「本地文档库位置」选择该文件夹，即可沿用 PDF、批注、译文、对话和分类信息，无需逐份导入。建议事先备份整个文档库。也可先将整个库复制到新文件夹，再在安装时选择该副本。勿只复制 PDF；如果安装版已有资料，应通过应用内的迁移功能调整位置。

浏览器设置（API Key、模型名称、界面语言等）属于浏览器的本地存储，使用同一浏览器及 `http://127.0.0.1:8765/` 地址可继续使用；换浏览器需要重新填写。

## 本地构建

仅维护者构建时需要 Windows、64 位 Python 3.13、Node.js 22+。在项目根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File packaging/build.ps1
```

脚本创建独立 `.build-venv`，使用 `requirements-build.lock` 与 `package-lock.json`，生成图标、许可和源码包，再用 PyInstaller 构建程序、运行隔离冒烟测试、用 Inno Setup 生成安装包。首次构建会将经过 SHA256 和签名校验的官方 Inno Setup 编译器安装至项目 `tmp/build-tools` 目录。

可用 `-Python C:\Python313\python.exe` 指定解释器，`-InnoCompiler C:\tools\ISCC.exe` 指定现有 Inno Setup 7。已装好构建依赖时可用 `-SkipDependencies`。

无人值守首次安装可使用 `Ai4PDF-1.0.0-windows-x64-setup.exe /VERYSILENT /SUPPRESSMSGBOXES /LIBRARYDIR="D:\Ai4PDF Library"`。无效路径或试图切换已有资料的库会返回非零退出码；原配置保持不变。安装器使用 Windows 自带的 PowerShell 校验目录及原子保存 UTF-8 配置，不需要另装 Python。

产物在 `release/`：安装 EXE、便携 ZIP、Ai4PDF 源码 ZIP、对应版本的 PyMuPDF/MuPDF 源码包、第三方声明、SHA256 清单。源码归档按白名单生成，排除文档库、迁移位置文件、虚拟环境、缓存和日志。`dist/Ai4PDF/` 是未压缩运行目录。

版本号修改 `version.py`、`package.json` 和 `package-lock.json`；三个文件应一致。构建环境 Python 版本为 3.13，构建依赖更新后应重新生成锁文件并验证。

## 上传 GitHub

将项目根目录的源码上传为仓库根目录，不要上传 `data/`、`library-location.json`、`.venv/`、`.build-venv/`、`node_modules/`、`tmp/`、`dist/` 或 `release/`。已有 `.gitignore` 排除这些项目；本次同时生成的 `Ai4PDF-1.0.0-source.zip` 是可直接解压用于建仓库的干净源码。

仓库使用 AGPL-3.0，保留 LICENSE、NOTICE 及第三方许可证。创建 Release 时应同时上传安装包、便携包、Ai4PDF 源码和匹配的 PyMuPDF/MuPDF 源码，不要只发布 EXE。

`.github/workflows/release.yml` 在推送 `v1.0.0` 这类标签时构建并创建 **Release 草稿**，维护者核对后发布。若该标签的 Release 已存在，则保留其附件，不覆盖已发布文件；本次 CI 构建仍作为 Actions artifact 提供。也可手动运行流程，只下载构建产物。本地打包不会自动上传或发布。

## 校验下载文件

从同一 Release 下载 `SHA256SUMS.txt`，用 PowerShell 计算文件的 SHA256，并逐字符与清单对应行比较：

```powershell
Get-FileHash .\Ai4PDF-1.0.0-windows-x64-setup.exe -Algorithm SHA256
```

## 启动诊断

日志位于 `%LOCALAPPDATA%\Ai4PDF\logs\desktop.log`，最多保留三个约 1 MB 文件。日志不记录 API Key、PDF 内容或聊天内容。

端口被其他程序占用时，启动器会提示先退出旧程序；不会结束其他进程或自动换端口导致浏览器设置丢失。重复启动会打开已有窗口，不创建第二个本地服务。服务由 Waitress 托管，安装版不使用 Flask 开发服务器。

自动化验证可以设置 `AI4PDF_HOME` 到隔离目录，并运行 `Ai4PDF.exe --no-tray --no-browser --port 48765`；`AI4PDF_DATA` 仍可单独覆盖文档库路径。
