## Ai4PDF v1.1.1 · PDF_AI助手

本次修复双栏文章的段落切分，并改善 Windows 浏览器启动兼容性。

### 修复内容

- 修复跨栏大图里的长说明文字干扰分栏，导致下方双栏正文合并成大块的问题；每栏的正文段落分别插入译文，图片保留完整。
- 重新打开旧文档时自动更新布局缓存，保留段落编号、已有译文、原文与译文批注，以及手动切分设置。
- 修复 Windows 文件关联使网页脚本被当成普通文本，造成页面可打开但按钮无响应的问题。
- 改用同版本 PDF.js 的兼容构建，移除 JSON 模块导入属性依赖；浏览器功能不足时明确提示更新。
- 增加五种语言的前端启动提示、可复制诊断及本机日志。日志仅记录错误类别、浏览器版本和缺失功能，不记录 API Key 或文档内容。

### 安装升级

安装版可通过「设置 → 软件更新」检查并安装更新；也可从托盘退出旧版 Ai4PDF，然后运行 `Ai4PDF-1.1.1-windows-x64-setup.exe`，沿用原安装位置和已有文档库。无需卸载或重新导入 PDF。请继续使用原浏览器和原访问地址，以保留浏览器中的已保存设置。

重新打开出现问题的文档，布局缓存会自动更新。手动切分的页面继续使用手动布局；如需采用新的自动布局，可在该页的「调整切分」中恢复自动并保存。

安装包尚未代码签名。可使用同目录的 `SHA256SUMS.txt` 核对文件。对应应用源码、PyMuPDF / MuPDF 源码与第三方许可一并提供，沿用 AGPL-3.0 许可。

### English

Fixes long figure labels shifting the body-column divider and merging unrelated paragraphs. Layout caches refresh while paragraph IDs, translations, annotations and manual segmentation are retained. Includes Windows script MIME fixes, browser compatibility improvements and local frontend diagnostics. Upgrade through Settings → Software update, or quit the old app and install in place, retaining the existing library and browser profile.

### 繁體中文

修正跨欄圖中的說明文字干擾正文分欄，保留既有譯文、註解及手動切分；改善瀏覽器相容性並新增啟動診斷。可從設定檢查更新，或結束舊版後覆蓋安裝，沿用原文件庫及瀏覽器。

### 日本語

図のラベルが本文の段組みを誤判定させる問題を修正。既存の翻訳・注釈・手動分割を保持し、ブラウザー互換性と起動診断も改善しました。設定から更新するか、旧版を終了して上書きインストールし、同じライブラリとブラウザーを使用してください。

### 한국어

그림 속 설명 때문에 본문 열과 문단이 합쳐지는 문제를 수정했습니다. 기존 번역·주석·수동 분할을 유지하며 브라우저 호환성과 시작 진단을 개선했습니다. 설정에서 업데이트하거나 이전 버전을 종료하고 기존 위치에 설치하세요. 같은 라이브러리와 브라우저를 사용하세요.
