// Keep this dependency-free so module load/parse failures are visible.
(function () {
  'use strict';
  var panel = document.getElementById('startup-status');
  var title = document.getElementById('startup-title');
  var message = document.getElementById('startup-message');
  var details = document.getElementById('startup-details');
  var copy = document.getElementById('startup-copy');
  var locale = 'zh-CN';
  try { locale = localStorage.getItem('paperdesk.locale') || locale; } catch (_) {}
  var words = {
    'zh-CN': ['正在启动 Ai4PDF', '页面启动失败', '浏览器需要更新', '请更新 Edge 或 Chrome，使用新版浏览器打开本页。', '请按 Ctrl + F5 刷新；若仍失败，将下方诊断信息和 desktop.log 发给维护者。', '重新加载', '复制诊断', '已复制', '加载时间较长，请检查浏览器或刷新重试。'],
    'zh-TW': ['正在啟動 Ai4PDF', '頁面啟動失敗', '瀏覽器需要更新', '請更新 Edge 或 Chrome，使用新版瀏覽器開啟本頁。', '請按 Ctrl + F5 重新整理；若仍失敗，將下方診斷資訊與 desktop.log 提供給維護者。', '重新載入', '複製診斷', '已複製', '載入時間較長，請檢查瀏覽器或重新整理。'],
    'en': ['Starting Ai4PDF', 'The page could not start', 'Browser update required', 'Update Edge or Chrome and open this page in the updated browser.', 'Press Ctrl + F5 to reload. If this persists, share the diagnostics below and desktop.log with the maintainer.', 'Reload', 'Copy diagnostics', 'Copied', 'Loading is taking longer than expected. Check your browser or reload.'],
    'ja': ['Ai4PDF を起動中', 'ページを起動できません', 'ブラウザーの更新が必要です', 'Edge または Chrome を更新し、新しいブラウザーでこのページを開いてください。', 'Ctrl + F5 で再読み込みしてください。解決しない場合は下の診断情報と desktop.log を管理者に送ってください。', '再読み込み', '診断をコピー', 'コピーしました', '読み込みに時間がかかっています。ブラウザーを確認するか再読み込みしてください。'],
    'ko': ['Ai4PDF 시작 중', '페이지를 시작하지 못했습니다', '브라우저 업데이트 필요', 'Edge 또는 Chrome을 업데이트한 뒤 새 브라우저에서 이 페이지를 여세요.', 'Ctrl + F5로 새로고침하세요. 계속 실패하면 아래 진단 정보와 desktop.log를 관리자에게 보내 주세요.', '새로고침', '진단 복사', '복사됨', '로딩이 지연되고 있습니다. 브라우저를 확인하거나 새로고침하세요.']
  };
  var text = words[locale] || words.en;
  title.textContent = text[0];
  document.getElementById('startup-reload').textContent = text[5];
  copy.textContent = text[6];
  var ready = false, reported = {}, timer;
  var browser = navigator.userAgent.match(/Edg\/([\d.]+)/) || navigator.userAgent.match(/(?:Firefox|Chrome|Version)\/([\d.]+)/);
  var browserLabel = browser ? browser[0] : 'Other';
  function report(code, error, missing) {
    if (reported[code]) return;
    reported[code] = true;
    var errorType = error && /^(Error|TypeError|SyntaxError|ReferenceError|SecurityError|NetworkError|AbortError)$/.test(error.name) ? error.name : 'Unknown';
    if (typeof fetch === 'function') fetch('/api/frontend-diagnostics', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({code: code, errorType: errorType, missing: missing || []}), keepalive: true
    }).catch(function () {});
    return 'Ai4PDF frontend: ' + code + '\nBrowser: ' + browserLabel + '\nError: ' + errorType + '\nMissing: ' + (missing && missing.join(', ') || 'none');
  }
  function fail(code, error, missing) {
    clearTimeout(timer);
    panel.hidden = false;
    title.textContent = text[code === 'unsupported_browser' ? 2 : 1];
    message.textContent = text[code === 'unsupported_browser' ? 3 : code === 'load_timeout' ? 8 : 4];
    details.textContent = report(code, error, missing) || details.textContent;
    details.hidden = false; copy.hidden = false;
  }
  copy.onclick = function () {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(details.textContent).then(function () {copy.textContent = text[7];}, selectDetails);
    } else selectDetails();
  };
  function selectDetails() {
    var range = document.createRange(); range.selectNodeContents(details);
    var selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
  }
  // Fixed diagnostic codes only: never log error.message/stack, URLs or storage.
  window.addEventListener('error', function (event) {
    if (!ready) fail('runtime_error', event.error);
    else if (event.error) report('runtime_error', event.error);
  });
  window.addEventListener('unhandledrejection', function (event) {
    if (!ready) fail('runtime_error', event.reason);
    else report('runtime_error', event.reason);
  });
  var supported = {
    modules: 'noModule' in document.createElement('script'), fetch: typeof fetch === 'function',
    Promise: typeof Promise === 'function', Worker: typeof Worker === 'function',
    'Promise.withResolvers': typeof Promise !== 'undefined' && typeof Promise.withResolvers === 'function',
    ResizeObserver: typeof ResizeObserver === 'function', DOMMatrix: typeof DOMMatrix === 'function',
    dialog: typeof HTMLDialogElement !== 'undefined' && typeof HTMLDialogElement.prototype.showModal === 'function',
    popover: typeof HTMLElement.prototype.showPopover === 'function'
  };
  var missing = Object.keys(supported).filter(function (key) {return !supported[key];});
  if (missing.length) {fail('unsupported_browser', null, missing); return;}
  timer = setTimeout(function () {fail('load_timeout');}, 20000);
  import('./app.js?v=startup-2').then(function () {
    ready = true; clearTimeout(timer); panel.hidden = true; report('ready');
  }).catch(function (error) {fail('module_load', error);});
}());
