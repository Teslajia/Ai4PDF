## Ai4PDF v1.1.0 · PDF_AI助手

本版完善纯译文阅读：在译文中直接查看图片、表格和公式，并改进图表识别、参考文献跳转与阅读位置恢复。

### 本次更新

- **纯译文阅读**：原文 / 双语对照 / 纯译文三个视图。纯译文按阅读顺序保留识别到的原图、表格和独立公式，使用对应图注和表注译文，支持放大查看。
- **图表文字和批注**：有文字层的图表可以选择、复制、划线及批注，与原文共享标记；三个视图复用已有译文和折叠状态，切换不重复调用翻译 API。可导出仅译文 Markdown。
- **识别修复**：减少图例、刻度、轴标题及公式被拆成翻译片段；保持表格与标题关联；过滤 PDF 裁剪范围外的不可见图形，修复正文局部被误当图片放大的问题。小图及长图按原尺寸、窗口大小等比限制显示。
- **参考文献跳转**：支持 PDF 原生内链及可识别的编号式引用，多篇引用可以选择目标，底部可返回原阅读位置。
- **阅读位置恢复**：切换原文、双语、纯译文时定位对应位置；支持跳转后返回、缩放、刷新及重新打开文档时恢复位置。
- **模型与设置**：按模型及接口声明筛选思考强度，不支持的旧选项回到默认；统一设置弹窗圆角。五种语言的 README 和使用指南同步更新。

### 下载

| 文件 | 用途 |
| --- | --- |
| [Windows x64 安装包](https://github.com/Teslajia/Ai4PDF/releases/download/v1.1.0/Ai4PDF-1.1.0-windows-x64-setup.exe) | 推荐，Windows 10 / 11 x64；无需另装 Python 或 Node.js |
| [免安装 ZIP](https://github.com/Teslajia/Ai4PDF/releases/download/v1.1.0/Ai4PDF-1.1.0-windows-x64-portable.zip) | 完整解压后运行 `Ai4PDF.exe` |
| [Ai4PDF 源码](https://github.com/Teslajia/Ai4PDF/releases/download/v1.1.0/Ai4PDF-1.1.0-source.zip) | 对应本版本的源码与构建说明 |

### 升级与数据保留

- **v1.0.1 安装版**：设置 → 软件更新 → 检查更新 → 下载 → 安装更新并重启。
- **v1.0.0 或手动升级**：先从托盘退出旧程序，直接运行 v1.1.0 安装包覆盖安装，无需安装中间版本、卸载或重新导入文档。
- 升级沿用现有文档库、批注、译文、手动切分和保存的设置。继续使用原浏览器与本地访问地址，浏览器配置会保留；未勾选记住的 API Key 需重新输入。
- 重新打开旧文档会自动刷新识别缓存，旧译文和批注不删除。源码版与便携版请手动下载对应文件更新。

### 限制与校验

图内文字保留原样。Markdown 暂不嵌入图片和表格；不提供 OCR 或重新排版的双语 / 译文 PDF 导出。复杂版面仍可能需要手动调整。AI 功能需要自行配置 API，安装包不包含 API Key、用户文档或模型额度。

安装包尚未代码签名。下载 `SHA256SUMS.txt` 后，用 `Get-FileHash .\Ai4PDF-1.1.0-windows-x64-setup.exe -Algorithm SHA256` 核对校验值。Release 附有对应的 Ai4PDF、PyMuPDF、MuPDF 源码和第三方声明，许可为 AGPL-3.0。

### English

v1.1.0 adds a translation-only view with detected original figures, tables and display equations, larger previews, selectable text and shared annotations. It improves figure/equation recognition, ignores paths hidden by PDF clipping, limits excessive image enlargement, adds reference navigation with a return action, and restores reading positions across views. Reasoning levels follow model/endpoint capabilities, and settings dialog corners are consistent.

Upgrade from v1.0.1 through **Settings → Software updates**. v1.0.0 can be upgraded directly by quitting the old app and running the new installer. Your library, annotations, translations, manual segmentation and saved browser settings are preserved; use the same browser and local address. Unsaved API keys must be entered again. No OCR or re-typeset bilingual PDF export is included. Markdown does not embed artwork. [English README](https://github.com/Teslajia/Ai4PDF/blob/v1.1.0/README.en.md).

### 繁體中文

新增包含原圖、表格與獨立公式的純譯文，支援放大、選字及共用註解；改善圖表辨識與異常放大，新增引用跳轉、返回與閱讀位置還原，並依模型及介面能力提供思考強度。升級保留文件庫、譯文、註解與已存設定。v1.0.1 可在設定中檢查更新，v1.0.0 可直接覆蓋安裝本版。[繁體中文說明](https://github.com/Teslajia/Ai4PDF/blob/v1.1.0/README.zh-TW.md)。

### 日本語

元の図・表・数式を含む訳文表示、拡大、文字選択、共有注釈に対応しました。図表認識と過剰な拡大を修正し、参考文献への移動・復帰と読書位置の復元を追加。推論強度はモデルと API の対応状況に従います。更新時もライブラリ、翻訳、注釈、保存済み設定を保持します。v1.0.1 は設定から更新でき、v1.0.0 は本版を直接上書きインストールできます。[日本語 README](https://github.com/Teslajia/Ai4PDF/blob/v1.1.0/README.ja.md)。

### 한국어

원본 그림·표·수식을 포함한 번역 보기, 확대, 텍스트 선택과 공유 주석을 지원합니다. 그림 인식과 과도한 확대를 수정하고 참고 문헌 이동·돌아가기 및 읽던 위치 복원을 추가했습니다. 추론 강도는 모델과 API의 지원 범위에 맞춰 표시합니다. 업데이트 시 라이브러리, 번역, 주석과 저장된 설정을 유지합니다. v1.0.1은 설정에서 업데이트하고 v1.0.0은 본 버전을 직접 덮어 설치할 수 있습니다. [한국어 README](https://github.com/Teslajia/Ai4PDF/blob/v1.1.0/README.ko.md).
