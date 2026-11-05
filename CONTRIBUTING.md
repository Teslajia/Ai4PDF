# Contributing to Ai4PDF

欢迎反馈问题、改进文档或提交代码。请使用公开可分享的示例，不要提交 API Key、真实聊天记录或私密论文。

## 开发环境

Windows 下安装 Python 3.11+、Node.js 22+，运行 `setup.ps1`，再运行 `start.cmd`。安装包构建使用锁定的 Python 3.13 环境，详见 [RELEASE.md](RELEASE.md)。

| 文件 | 职责 |
| --- | --- |
| `app.py` | 本地接口、文档状态、AI 转发和批注导出 |
| `layout.py`、`translation_policy.py`、`manual_layout.py` | 自动排版、翻译筛选与手动分块 |
| `library.py` | 文档分类、回收站和迁移 |
| `static/` | 阅读、双语、批注、助手和本地化界面 |
| `desktop.py`、`runtime_paths.py` | Windows 启动与数据目录 |
| `packaging/` | EXE、安装程序、源码归档和发布验证 |
| `tests/` | 后端及真实浏览器回归测试 |

## 验证修改

```powershell
.\.venv\Scripts\python.exe -m pip install pytest playwright
npm run check
.\.venv\Scripts\python.exe -m pytest tests -q
```

浏览器测试使用本机 Chrome 或 Edge，在独立上下文和临时库中运行，不调用真实模型 API。Windows 安装流程测试使用独立测试 AppId，不覆盖正式安装。

不要用个人文档库测试删除、迁移或数据转换。使用 `AI4PDF_HOME`、`AI4PDF_DATA` 或现有测试夹具指定临时目录。

## Issue 和 Pull Request

- 说明版本、系统、复现步骤、预期与实际表现。模型问题提供服务类型和模型 ID 即可，**不要提供 Key**。
- 提供可公开的最小示例或项目示例 PDF；截图遮盖私人文件名、对话和账号信息。
- PR 描述用户可观察到的变化及验证结果。界面文字修改同步检查五种语言。
- 保持文档、段落 ID、批注和迁移兼容性，避免删除旧数据。
- 新增发行文件时更新 `packaging/prepare_release.py` 的源码白名单，不提交文档库、虚拟环境、缓存或构建产物。

项目采用 AGPL-3.0，贡献需可按该许可证发布，并保留第三方许可声明。

English contributions are welcome. Include a concise change description, reproduction steps and relevant validation. Never attach credentials or private documents.
