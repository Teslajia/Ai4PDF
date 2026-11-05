import * as pdfjs from '/vendor/pdfjs-dist/build/pdf.mjs';
import { renderChatMarkdown } from './chat-markdown.js';
import renderMathInElement from '/vendor/katex/dist/contrib/auto-render.mjs';
import { sourceTextPage, mountSourceText, scaleSourceCrop, selectedTextAnchor, paintTextAnnotations, sourceSelection } from './selection.js';
import { ChatImages, appendMessageImages } from './chat-images.js';
import { LayoutEditor } from './layout-editor.js';
import { ModelPicker } from './model-picker.js';
import { LibraryUI } from './library.js';
import { draggableDialog } from './draggable-dialog.js';
import { AnnotationActions } from './annotation-actions.js';
import { t, getLocale, setLocale, startI18n } from './i18n.js';

pdfjs.GlobalWorkerOptions.workerSrc = '/vendor/pdfjs-dist/build/pdf.worker.mjs';
const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const icon = name => `<svg><use href="#i-${name}"/></svg>`;
const escapeHTML = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let doc = null, pdf = null, mode = 'pdf', currentPage = 1, drawer = '', pageViews = new Map();
let selection = null, quotedText = '', annotationEdit = null, observer, renderGeneration = 0, opening = false;
let translating = false, pauseTranslation = false, translationAbort = null, chatAbort = null, chatBusy = false;
let toastTimer, scrollTimer, resizeTimer, autoSave = Promise.resolve();
let config = {};
let retryDraft=null;
let collapsedTranslations=new Set();
try{const saved=JSON.parse(localStorage.getItem('paperdesk.collapsedTranslations')||'[]');if(Array.isArray(saved))collapsedTranslations=new Set(saved.filter(key=>typeof key==='string'));}catch{}
let translationLayout = {id:null,data:null,promise:null,error:false};
let translationImageObserver = null;
let sourceTextCache=new Map(), bilingualGeneration=0;
const bilingualResizeObserver=new ResizeObserver(entries=>{
  for(const {target} of entries)if(target.classList.contains('source-crop'))scaleSourceCrop(target);else drawTranslationAnnotations(target);
});
try { config = JSON.parse(localStorage.getItem('paperdesk.config') || '{}'); } catch { /* invalid old settings */ }
config = { baseUrl:'', model:'', displayName:'', reasoningEffort:'default', recentModels:[], apiKey:'', rememberKey:false, ...config };
const reasoningLabels = {default:'跟随模型默认',none:'关闭（none）',minimal:'极低（minimal）',low:'低（low）',medium:'中（medium）',high:'高（high）',xhigh:'极高（xhigh）',max:'最高（max）'};
if(!Object.hasOwn(reasoningLabels,config.reasoningEffort))config.reasoningEffort='default';
config.recentModels=Array.isArray(config.recentModels)?config.recentModels.filter(m=>typeof m==='string'&&m.trim()).slice(0,12):[];
for(const select of [$('#quick-reasoning'),$('#api-reasoning')]){
  for(const [value,label] of Object.entries(reasoningLabels))select.add(new Option(label,value));
}
const initialChat = $('#messages').innerHTML;
const noteWindow=draggableDialog($('#note-dialog'),$('#note-dialog .note-drag-handle'));
const annotationActions=new AnnotationActions({roots:[$('#pages'),$('#paragraphs')],getDocument:()=>doc,edit:openNote,onShow:()=>{$('#selection-toolbar').hidden=true;}});
const libraryUI=new LibraryUI({api,notify:toast,busy:()=>chatBusy||translating||opening,flush:()=>autoSave,openDocument:openById,onChange:async documents=>{
  const current=documents.find(d=>d.id===doc?.id&&!d.deletedAt);
  if(doc&&!current)await closeDocument();
  else if(doc&&current){doc.title=current.title;$('#doc-title').textContent=current.title;}
  if(drawer==='library')await renderDrawer();
}});
const chatImages=new ChatImages({api,notify:toast,busy:()=>chatBusy,documentId:()=>doc?.id});
const translationParagraphs=()=>doc?.translationParagraphs || doc?.paragraphs || [];
const layoutEditor=new LayoutEditor({api,notify:toast,documentId:()=>doc?.id,busy:()=>translating||opening,onSave:async(result,number,id)=>{
  if(doc?.id!==id)return;
  doc.translationParagraphs=result.translationParagraphs;doc.manualPages=result.manualPages;doc.manualRevision=result.manualRevision;
  translationLayout={id,data:result.layout,promise:null,error:false};
  renderParagraphs();if(drawer==='annotations')renderDrawer();
  document.querySelector(`.bilingual-page[data-source-page="${number}"]`)?.scrollIntoView({block:'start'});
}});

function toast(message, error=false) {
  clearTimeout(toastTimer); $('#toast').textContent = message; $('#toast').classList.toggle('error', error);
  $('#toast').hidden = false; toastTimer = setTimeout(() => $('#toast').hidden = true, error ? 6500 : 3500);
}
async function api(url, options={}) {
  const opts = {...options};
  if (opts.body && !(opts.body instanceof FormData)) { opts.body = JSON.stringify(opts.body); opts.headers = {'Content-Type':'application/json', ...opts.headers}; }
  const response = await fetch(url, opts);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.error || `请求失败 (${response.status})`);
  }
  return response.json();
}
function requireDoc() { if (doc) return true; toast('请先打开一份 PDF。'); return false; }
function requireConfig() {
  if (config.baseUrl && config.model) return true;
  openSettings(); toast('先设置 API 地址和模型，即可使用 AI。'); return false;
}
function busyLoading(value, text='正在读取 PDF 并提取段落…') { $('#loading').hidden = !value; $('#loading-text').textContent = text; }
function saveState(fields) {
  if (!doc) return Promise.resolve();
  const id = doc.id;
  $('#save-status').textContent = '正在保存…';
  autoSave = autoSave.catch(() => {}).then(() => api(`/api/documents/${id}/state`, {method:'PATCH', body:fields}))
    .then(() => { if (doc?.id===id) $('#save-status').textContent='阅读记录已保存到本机'; })
    .catch(e => { $('#save-status').textContent='保存失败'; toast(e.message,true); });
  return autoSave;
}
async function importFile(file) {
  if (!file || opening) return;
  if (chatBusy || translating) return toast('请先停止问答或暂停翻译，再切换文档。');
  if (file.size > 100*1024*1024) return toast('PDF 最大支持 100 MB。',true);
  opening=true; busyLoading(true);
  try { const form=new FormData(); form.append('file', file); const data=await api('/api/documents',{method:'POST',body:form}); await openDocument(data); }
  catch(e) { toast(e.message,true); } finally { opening=false; busyLoading(false); $('#file-input').value=''; }
}
async function openById(id) {
  if (opening) return;
  if (chatBusy || translating) return toast('请先停止问答或暂停翻译，再切换文档。');
  opening=true; busyLoading(true);
  try { await openDocument(await api(`/api/documents/${id}`)); }
  catch(e) { toast(e.message,true); } finally { opening=false; busyLoading(false); }
}
async function openDocument(data) {
  annotationActions.hide();
  await autoSave;
  const loadingTask = pdfjs.getDocument({url:`/api/documents/${data.id}/pdf`, cMapUrl:'/vendor/pdfjs-dist/cmaps/', cMapPacked:true,
    standardFontDataUrl:'/vendor/pdfjs-dist/standard_fonts/', wasmUrl:'/vendor/pdfjs-dist/wasm/', isEvalSupported:false});
  let loaded;
  try { loaded=await loadingTask.promise; }
  catch(error) {
    // Release the failed load's worker while keeping the previous PDF usable.
    await loadingTask.destroy().catch(()=>{});
    throw error;
  }
  renderGeneration++; observer?.disconnect();
  bilingualGeneration++;translationImageObserver?.disconnect();bilingualResizeObserver.disconnect();
  clearTimeout(scrollTimer);clearTimeout(resizeTimer);
  // Invalidate pending layout/text callbacks before destroying the old transport.
  sourceTextCache=new Map();
  translationLayout={id:data.id,data:null,promise:null,error:false};
  for (const v of pageViews.values()) { v.task?.cancel(); v.textLayer?.cancel(); }
  // PDF.js 6 owns document teardown on PDFDocumentLoadingTask, not its proxy.
  try { if(pdf)await pdf.loadingTask.destroy(); }
  catch(error) { await loadingTask.destroy().catch(()=>{});throw error; }
  pdf=loaded; doc=data; currentPage=doc.state.page || 1; selection=null; setQuote('');chatImages.clear();retryDraft=null;$('#question').value='';
  clearTimeout(toastTimer);$('#toast').hidden=true;
  localStorage.setItem('paperdesk.last',doc.id);
  $('#doc-title').dataset.userContent='';$('#doc-title').textContent=doc.title; $('#doc-title').title=doc.name;
  $('#save-status').textContent='阅读记录已保存到本机'; $('#page-total').textContent=doc.pageCount;
  $('#page-number').max=doc.pageCount; $('#page-number').value=currentPage;
  for (const id of ['export','prev','next','page-number']) $(`#${id}`).disabled=false;
  $('#welcome').hidden=true; $('#context-status').innerHTML=icon('file')+`${doc.pageCount} 页 · ${doc.paragraphs.length} 段`;
  $('#reader-meta').textContent=`${doc.pageCount} 页 · ${doc.paragraphs.length} 个文字段落`;
  $('#reader-hint').textContent=doc.paragraphs.length ? '选中文字即可高亮、批注或向 AI 提问' : '未提取到文字：扫描版需要先进行 OCR';
  restoreTranslationRange();
  renderMessages(); updateAnnotationCount(); closeDrawer(); switchMode('pdf');
  await buildPages(); renderParagraphs();
  if (!doc.paragraphs.length) toast('这份 PDF 没有可提取的文字。可阅读原版，翻译和文字问答需要先 OCR。',true);
}
async function closeDocument(){
  annotationActions.hide();
  clearTimeout(scrollTimer);clearTimeout(resizeTimer);renderGeneration++;bilingualGeneration++;
  observer?.disconnect();translationImageObserver?.disconnect();bilingualResizeObserver.disconnect();
  for(const v of pageViews.values()){v.task?.cancel();v.textLayer?.cancel();}
  const previous=pdf;pdf=null;doc=null;pageViews=new Map();sourceTextCache=new Map();
  translationLayout={id:null,data:null,promise:null,error:false};selection=null;annotationEdit=null;retryDraft=null;
  localStorage.removeItem('paperdesk.last');chatImages.clear();setQuote('');$('#question').value='';
  $('#pages').replaceChildren();$('#paragraphs').replaceChildren();$('#welcome').hidden=false;
  $('#doc-title').removeAttribute('data-user-content');$('#doc-title').removeAttribute('title');$('#doc-title').textContent='你的下一次发现，从这里开始';$('#save-status').textContent='PDF_AI助手';
  $('#page-total').textContent='—';$('#page-number').value=1;$('#annotation-count').hidden=true;
  for(const id of ['export','prev','next','page-number'])$(`#${id}`).disabled=true;
  $('#reader-meta').textContent='专注阅读，自由探索';$('#reader-hint').textContent='PDF 保存在本机 · AI 仅连接你设置的服务';$('#context-status').innerHTML=icon('file')+'打开 PDF 后即可提问';
  renderMessages();switchMode('pdf');if(previous)await previous.loadingTask.destroy().catch(()=>{});
}
function switchMode(value) {
  annotationActions.hide();
  if (value==='translation' && !requireDoc()) return;
  mode=value; $('#pdf-tab').classList.toggle('active',value==='pdf'); $('#translation-tab').classList.toggle('active',value==='translation');
  $('#pdf-scroll').hidden=value!=='pdf' || !doc; $('#translation-view').hidden=value!=='translation';
  $('#pdf-tools').hidden=value!=='pdf'; $('#translation-tools').hidden=value!=='translation';
  $('#selection-toolbar').hidden=true;
  if(value==='translation')renderParagraphs();
}

async function buildPages() {
  annotationActions.hide();
  if (!pdf) return;
  const generation=++renderGeneration;
  observer?.disconnect();
  for (const v of pageViews.values()) { v.task?.cancel(); v.textLayer?.cancel(); }
  pageViews=new Map(); $('#pages').replaceChildren();
  const width=Math.max(220,$('#pdf-scroll').clientWidth-50);
  for (let n=1;n<=doc.pageCount;n++) {
    const size=doc.pages[n-1], zoom=$('#zoom').value;
    const scale=zoom==='fit' ? Math.min(width/size.width,1.7) : Number(zoom);
    const el=document.createElement('div'); el.className='page'; el.dataset.pageNumber=n;
    el.style.width=`${size.width*scale}px`; el.style.height=`${size.height*scale}px`;
    el.style.setProperty('--scale-factor',scale); el.style.setProperty('--user-unit','1');
    el.innerHTML=`<div class="page-placeholder">第 ${n} 页</div><span class="page-label">${n} / ${doc.pageCount}</span>`;
    $('#pages').append(el); pageViews.set(n,{el,scale,rendered:false,rendering:false,generation});
  }
  let active=0; const queue=[];
  const pump=() => {
    while (queue.length && active<2 && generation===renderGeneration) {
      const n=queue.shift(); active++;
      renderPage(n,generation).catch(e=>{ if (e.name!=='RenderingCancelledException' && generation===renderGeneration) toast('页面渲染失败：'+e.message,true); })
        .finally(()=>{ active--; pump(); });
    }
  };
  observer=new IntersectionObserver(entries=>{
    for (const entry of entries) {
      const n=Number(entry.target.dataset.pageNumber), v=pageViews.get(n);
      if (entry.isIntersecting && v && !v.rendered && !v.rendering && !queue.includes(n)) queue.push(n);
    }
    pump();
  },{root:$('#pdf-scroll'),rootMargin:'700px 0px'});
  for (const v of pageViews.values()) observer.observe(v.el);
  goPage(currentPage,false);
  await renderPage(currentPage,generation);
}
async function renderPage(n,generation) {
  const v=pageViews.get(n);
  if (!v || v.rendered || v.rendering || generation!==renderGeneration) return;
  v.rendering=true;
  try {
    const page=await pdf.getPage(n);
    if (generation!==renderGeneration) return;
    const viewport=page.getViewport({scale:v.scale}); v.viewport=viewport;
    v.el.style.width=`${viewport.width}px`; v.el.style.height=`${viewport.height}px`;
    const canvas=document.createElement('canvas'), dpr=Math.min(window.devicePixelRatio||1,2);
    canvas.width=Math.ceil(viewport.width*dpr); canvas.height=Math.ceil(viewport.height*dpr);
    canvas.style.width=`${viewport.width}px`; canvas.style.height=`${viewport.height}px`;
    v.el.append(canvas);
    v.task=page.render({canvasContext:canvas.getContext('2d'),viewport,transform:dpr===1 ? null : [dpr,0,0,dpr,0,0]});
    await v.task.promise;
    if (generation!==renderGeneration) return;
    const textContent=await page.getTextContent();
    if (generation!==renderGeneration) return;
    // Explicit fallback families keep canvas measurement and DOM glyph metrics identical.
    const families={'sans-serif':'Arial',serif:'Times New Roman',monospace:'Courier New'};
    for(const style of Object.values(textContent.styles)) if(families[style.fontFamily]) style.fontFamily=families[style.fontFamily];
    const textContainer=document.createElement('div'); textContainer.className='textLayer';
    // Match PDF.js's measuring canvas language; inheriting zh-CN changes generic font metrics.
    textContainer.lang=textContent.lang || ''; v.el.append(textContainer);
    v.textLayer=new pdfjs.TextLayer({textContentSource:textContent,container:textContainer,viewport});
    await v.textLayer.render();
    if (generation!==renderGeneration) return;
    const layer=document.createElement('div'); layer.className='annotation-overlays'; v.el.append(layer);
    const links=document.createElement('div'); links.className='link-overlays'; v.el.append(links);
    const annotations=await page.getAnnotations();
    if (generation!==renderGeneration) return;
    for (const a of annotations) {
      if (a.subtype!=='Link' || (!a.url && !a.dest)) continue;
      // PDF.js 6 removed convertToViewportRectangle. Transform both corners
      // using the supported point API, including page rotation and crop offsets.
      if (!Array.isArray(a.rect) || a.rect.length!==4 || !a.rect.every(Number.isFinite)) continue;
      const rect=[...viewport.convertToViewportPoint(a.rect[0],a.rect[1]),
        ...viewport.convertToViewportPoint(a.rect[2],a.rect[3])], link=document.createElement('a');
      link.style.cssText=`left:${Math.min(rect[0],rect[2])}px;top:${Math.min(rect[1],rect[3])}px;width:${Math.abs(rect[2]-rect[0])}px;height:${Math.abs(rect[3]-rect[1])}px`;
      link.title=a.url || '跳转到引用';
      if (a.url && /^https?:\/\//i.test(a.url)) {link.href=a.url;link.target='_blank';link.rel='noopener noreferrer';}
      else if (a.dest) { link.href='#'; link.onclick=async e=>{e.preventDefault();try{const dest=typeof a.dest==='string'?await pdf.getDestination(a.dest):a.dest;if(dest)goPage(typeof dest[0]==='number'?dest[0]+1:await pdf.getPageIndex(dest[0])+1);}catch{toast('无法定位该引用。');}}; }
      else continue;
      links.append(link);
    }
    v.el.querySelector('.page-placeholder')?.remove(); v.rendered=true; drawAnnotations(n);
  } catch(error) {
    if(generation===renderGeneration)throw error;
  } finally { v.rendering=false; }
}
function goPage(n,persist=true) {
  if (!doc) return;
  n=Math.max(1,Math.min(doc.pageCount,Number(n)||1)); currentPage=n;
  switchMode('pdf'); $('#page-number').value=n;
  const v=pageViews.get(n); if (v) $('#pdf-scroll').scrollTop=v.el.offsetTop-$('#pages').offsetTop;
  if (persist) saveState({page:n});
}
function onScroll() {
  clearTimeout(scrollTimer); $('#selection-toolbar').hidden=true;
  scrollTimer=setTimeout(()=>{
    if (!doc || mode!=='pdf') return;
    const y=$('#pdf-scroll').getBoundingClientRect().top+100;
    const page=[...pageViews.entries()].find(([,v])=>v.el.getBoundingClientRect().bottom>y);
    if (page && currentPage!==page[0]) { currentPage=page[0]; $('#page-number').value=currentPage; saveState({page:currentPage}); }
    // Release distant high-resolution canvases; IntersectionObserver reloads them on return.
    for (const [n,v] of pageViews) if (Math.abs(n-currentPage)>5 && v.rendered) {
      v.textLayer?.cancel(); for (const el of v.el.querySelectorAll('canvas,.textLayer,.annotation-overlays,.link-overlays')) el.remove();
      v.rendered=false; v.textLayer=null; observer.unobserve(v.el); observer.observe(v.el);
    }
  },180);
}

function drawAnnotations(n) {
  const layers=[pageViews.get(n)?.el.querySelector('.annotation-overlays'),...$$(`.bilingual-page[data-source-page="${n}"] .annotation-overlays`)].filter(Boolean);
  for(const layer of layers){
    layer.replaceChildren();
    for (const a of doc.state.annotations.filter(a=>a.source!=='translation' && a.page===n)) for (const r of a.rects) {
    const mark=document.createElement('div'); mark.className=`annotation-mark ${a.kind}`;mark.dataset.annotationId=a.id;
    mark.style.cssText=`left:${r[0]*100}%;top:${r[1]*100}%;width:${r[2]*100}%;height:${r[3]*100}%;background:${a.color};border-color:${a.color}`;
    mark.title=a.note || a.text; if (a.kind==='note') mark.textContent='✎'; layer.append(mark);
    }
  }
  for(const p of translationParagraphs().filter(p=>p.page===n))drawTranslationAnnotations($(`#para-${p.id} .translated-text`));
}
function drawTranslationAnnotations(el) {
  if(!el || !doc)return;
  const paragraphId=el.closest('.paragraph').dataset.paragraphId,language=$('#target-language').value;
  paintTextAnnotations(el,doc.state.annotations.filter(a=>a.source==='translation' && a.paragraphId===paragraphId && a.language===language),doc.state.translations[`${language}:${paragraphId}`]);
}
function updateAnnotationCount() {
  const count=doc?.state.annotations.length || 0; $('#annotation-count').textContent=count; $('#annotation-count').hidden=!count;
}
function captureSelection() {
  selection=null;$('#selection-toolbar').hidden=true;
  const selected=window.getSelection();
  if (!selected?.rangeCount || selected.isCollapsed || !doc) return;
  annotationActions.hide();
  const range=selected.getRangeAt(0), text=selected.toString().trim();
  const ancestor=range.commonAncestorContainer.nodeType===1 ? range.commonAncestorContainer : range.commonAncestorContainer.parentElement;
  if(!text || !ancestor?.closest('#pages,#paragraphs'))return;
  const translation=ancestor.closest('.translated-text');let groups;
  if(translation){
    if(translation.matches('.pending,.failed'))return;
    const anchor=selectedTextAnchor(translation,range);if(!anchor?.text.trim())return;
    const paragraphId=translation.closest('.paragraph').dataset.paragraphId,language=$('#target-language').value;
    groups=[{source:'translation',paragraphId,language,translationText:doc.state.translations[`${language}:${paragraphId}`],...anchor}];
  }else{
    if(ancestor.closest('#paragraphs') && $$('.translated-text,.paragraph-meta,.bilingual-page-heading').some(el=>range.intersectsNode(el))){
      toast('请在同一段译文内选择，或单独选择一块原文后批注。');return;
    }
    const views=mode==='pdf'?[...pageViews].filter(([,v])=>v.rendered).map(([number,v])=>({number,element:v.el,viewport:v.viewport})):
      $$('.source-page-plane').filter(el=>el.pdfViewport).map(element=>({number:Number(element.closest('.bilingual-page').dataset.sourcePage),element,viewport:element.pdfViewport,clipElement:element.parentElement}));
    groups=sourceSelection(range,views);
  }
  if (!groups.length) return;
  selection={text:groups.map(g=>g.text).join('\n'),groups}; const bounds=range.getBoundingClientRect(), toolbar=$('#selection-toolbar');
  $('#selection-source').textContent=translation?'译文':'原文';
  toolbar.hidden=false; toolbar.style.left=`${Math.max(8,Math.min(window.innerWidth-toolbar.offsetWidth-8,bounds.left))}px`;
  toolbar.style.top=`${Math.max(80,Math.min(window.innerHeight-60,bounds.top-48))}px`;
}
async function addAnnotation(kind,note='') {
  if (!selection || !doc) return false;
  const captured=selection, id=doc.id, color=$('#annotation-color').value;
  $('#selection-toolbar').hidden=true;
  try {
    for (const group of captured.groups) {
      const annotation=await api(`/api/documents/${id}/annotations`,{method:'POST',body:{...group,kind,note,color}});
      if(doc?.id!==id)return false;
      doc.state.annotations.push(annotation); drawAnnotations(annotation.page);
    }
    updateAnnotationCount(); $('#save-status').textContent='批注已保存到本机';
    if(drawer==='annotations') renderDrawer();
    window.getSelection()?.removeAllRanges(); selection=null; toast(captured.groups[0].source==='translation'?'译文批注已保存，可随双语 Markdown 导出。':'批注已保存，可随 PDF 导出。');return true;
  } catch(e) { toast(e.message,true);return false; }
}
function openNote(annotation=null) {
  annotationActions.hide();
  $('#selection-toolbar').hidden=true;
  annotationEdit=annotation; $('#note-quote').textContent=annotation?.text || selection?.text || '';
  $('#note-text').value=annotation?.note || ''; $('#note-dialog').showModal(); noteWindow.fit(); $('#note-text').focus({preventScroll:true});
}
function setQuote(text) {
  quotedText=text; $('#selection-context').hidden=!text; $('#selection-context span').textContent=text;
}

function closeDrawer() {drawer='';$('#drawer').hidden=true;$$('[data-drawer]').forEach(b=>b.classList.remove('active'));}
async function toggleDrawer(value) {
  if (drawer===value) return closeDrawer();
  drawer=value; $('#drawer').hidden=false;
  $$('[data-drawer]').forEach(b=>b.classList.toggle('active',b.dataset.drawer===value));
  $('#drawer-title').textContent={library:'本地文档库',outline:'文档目录',annotations:'我的批注',search:'搜索原文'}[value];
  await renderDrawer();
}
async function renderDrawer() {
  const area=$('#drawer-content'); area.replaceChildren();
  if (drawer==='library') {
    const docs=await api('/api/documents'); if(drawer!=='library') return;
    const manage=document.createElement('button');manage.className='button library-launch';manage.id='library-manage';manage.textContent='管理文档库';manage.onclick=()=>libraryUI.open();area.append(manage);
    if(!docs.length) {area.insertAdjacentHTML('beforeend','<div class="drawer-empty">还没有文档。打开一份 PDF，它会自动保存在这里。</div>');return;}
    for(const d of docs) {
      const b=document.createElement('button');b.className='document-card'+(doc?.id===d.id?' active':'');
      b.innerHTML=`<strong>${escapeHTML(d.title)}</strong><small>${d.pageCount} 页 · ${new Date(d.created).toLocaleDateString('zh-CN')}</small>`;
      b.onclick=()=>openById(d.id);area.append(b);
    }
  } else if (!doc) {area.innerHTML='<div class="drawer-empty">打开 PDF 后即可使用。</div>';}
  else if(drawer==='outline') {
    const outline=doc.outline.length?doc.outline:Array.from({length:doc.pageCount},(_,i)=>[1,`第 ${i+1} 页`,i+1]);
    for(const [level,title,page] of outline) {const b=document.createElement('button');b.className='outline-item';if(!doc.outline.length)b.dataset.uiOutline='';b.textContent=title;b.style.paddingLeft=`${8+Math.min(level-1,4)*12}px`;b.onclick=()=>goPage(page);area.append(b);}
  } else if(drawer==='annotations') {
    if(!doc.state.annotations.length) area.innerHTML='<div class="drawer-empty">在 PDF、双语图文的原文或译文中拖选文字，就能高亮、划线或写批注。<br><br>原文批注随 PDF 导出；译文批注随双语 Markdown 导出。</div>';
    for(const a of [...doc.state.annotations].sort((a,b)=>a.page-b.page)) {
      const card=document.createElement('div'); card.className='annotation-card';
      const translated=a.source==='translation',p=translationParagraphs().find(p=>p.id===a.paragraphId);
      const skipped=translated && (!p || p.translatable===false),stale=translated && translationValue(p,a.language)!==a.translationText;
      card.innerHTML=`<div class="annotation-meta"><button class="page-link">第 ${a.page} 页 ↗</button><span>${translated?'译文 · ':''}${{highlight:'高亮',underline:'下划线',note:'备注'}[a.kind]}</span></div>${translated?`<small class="annotation-origin">${escapeHTML(a.language)} · ${!p?'切分已调整，保留旧批注':skipped?'此段保留原貌，不再翻译':stale?'译文已更新，保留旧批注':'随双语 Markdown 导出'}</small>`:''}<blockquote>${escapeHTML(a.text)}</blockquote>${a.note?`<p>${escapeHTML(a.note)}</p>`:''}<div class="annotation-actions"><button class="edit">编辑备注</button><button class="delete">删除</button></div>`;
      card.querySelector('.page-link').onclick=async()=>{
        if(!translated || skipped)return goPage(a.page);
        if(translating && $('#target-language').value!==a.language)return toast('请先暂停翻译，再切换到这条批注的语言。');
        $('#target-language').value=a.language;switchMode('translation');
        await translationLayout.promise;
        if(p)setTranslationCollapsed(p,false);
        $(`#para-${a.paragraphId}`)?.scrollIntoView({block:'center'});
        if(stale)toast('译文已更新。这条批注保留了旧选文，不再标记当前译文。');
      };
      card.querySelector('.edit').onclick=()=>openNote(a);
      card.querySelector('.delete').onclick=async()=>{try{await api(`/api/documents/${doc.id}/annotations/${a.id}`,{method:'DELETE'});doc.state.annotations=doc.state.annotations.filter(x=>x.id!==a.id);drawAnnotations(a.page);updateAnnotationCount();renderDrawer();}catch(e){toast(e.message,true);}};
      area.append(card);
    }
  } else if(drawer==='search') {
    area.innerHTML='<input class="search-input" placeholder="搜索关键词…" aria-label="搜索关键词"><div id="search-results"></div>';
    const input=area.querySelector('input');input.focus();input.oninput=()=>{
      const q=input.value.trim().toLowerCase(), result=$('#search-results');result.replaceChildren();if(!q)return;
      const matches=doc.paragraphs.filter(p=>p.text.toLowerCase().includes(q));
      for(const p of matches.slice(0,100)){const b=document.createElement('button');b.className='document-card';const at=p.text.toLowerCase().indexOf(q);b.innerHTML=`<small>第 ${p.page} 页</small><strong>${escapeHTML(p.text.slice(Math.max(0,at-35),at+120))}</strong>`;b.onclick=()=>goPage(p.page);result.append(b);}
      if(!matches.length)result.innerHTML='<div class="drawer-empty">没有找到相关文字。</div>';
    };
  }
}

function translationKey(p) {return `${$('#target-language').value}:${p.id}`;}
function translationValue(p,language=$('#target-language').value) {
  if(!p || p.translatable===false)return '';
  const key=`${language}:${p.id}`,savedSource=doc.state.translationSources?.[key];
  if(p.translationSourceHash && savedSource!==p.translationSourceHash && (savedSource || p.translationSource!==p.text))return '';
  return doc.state.translations[key] || '';
}
function translationRange() {
  const start=Number($('#translation-from').value), end=Number($('#translation-to').value);
  const valid=!!doc && Number.isInteger(start) && Number.isInteger(end) && start>=1 && end>=start && end<=doc.pageCount;
  return {start,end,valid,full:valid && start===1 && end===doc.pageCount};
}
function rangeParagraphs(range=translationRange()) {
  return range.valid ? translationParagraphs().filter(p=>p.translatable!==false && p.page>=range.start && p.page<=range.end) : [];
}
function restoreTranslationRange() {
  let saved=null;
  try{saved=JSON.parse(localStorage.getItem(`paperdesk.range.${doc.id}`));}catch{/* Use the full document for invalid saved ranges. */}
  $('#translation-from').max=$('#translation-to').max=doc.pageCount;
  $('#translation-from').value=saved?.start ?? 1; $('#translation-to').value=saved?.end ?? doc.pageCount;
  if(!translationRange().valid){$('#translation-from').value=1;$('#translation-to').value=doc.pageCount;}
}
function changeTranslationRange() {
  if(!doc)return;
  const range=translationRange();
  if(range.valid)localStorage.setItem(`paperdesk.range.${doc.id}`,JSON.stringify({start:range.start,end:range.end}));
  updateTranslationProgress();
}
function ensureTranslationLayout() {
  const state=translationLayout;
  if(state.promise || state.data || state.error || !doc)return;
  $('#translation-display-hint').textContent='正在分析页面布局…';
  state.promise=api(`/api/documents/${doc.id}/layout`).then(data=>{
    if(translationLayout!==state)return;
    state.data=data;
    if($('#translation-display').value==='layout')renderParagraphs();
  }).catch(e=>{
    if(translationLayout!==state)return;
    state.error=true;
    $('#translation-display-hint').textContent='图文布局加载失败，暂时显示文字。切换显示方式可重试。';
    toast(e.message,true);
  }).finally(()=>{state.promise=null;});
}
function translationFoldKey(p){return JSON.stringify([doc.id,$('#target-language').value,p.id]);}
function applyTranslationFold(card,p){
  const collapsed=collapsedTranslations.has(translationFoldKey(p)),button=card.querySelector('.translation-toggle');
  card.querySelector('.translated-text').hidden=collapsed;
  card.classList.toggle('translation-collapsed',collapsed);
  button.textContent=collapsed?'展开':'折叠';button.title=collapsed?'展开译文':'折叠译文';
  button.setAttribute('aria-expanded',String(!collapsed));
}
function setTranslationCollapsed(p,collapsed){
  const key=translationFoldKey(p),card=$(`#para-${p.id}`);
  collapsed?collapsedTranslations.add(key):collapsedTranslations.delete(key);
  try{localStorage.setItem('paperdesk.collapsedTranslations',JSON.stringify([...collapsedTranslations]));}catch{}
  if(!card)return;
  const text=card.querySelector('.translated-text'),selected=window.getSelection();
  if(collapsed&&selected?.rangeCount&&selected.getRangeAt(0).intersectsNode(text)){selected.removeAllRanges();selection=null;}
  $('#selection-toolbar').hidden=true;annotationActions.hide();
  applyTranslationFold(card,p);
  if(!collapsed)drawTranslationAnnotations(text);
}
function paragraphCard(p,original=true) {
  const card=document.createElement('article');card.className='paragraph';card.id=`para-${p.id}`;
  card.dataset.paragraphId=p.id;
  card.innerHTML=`<div class="paragraph-meta"><span>${original?'原文':'译文'}</span><button class="source-page">第 ${p.page} 页 ↗</button><button type="button" class="translation-toggle" aria-controls="translation-${p.id}" aria-expanded="true">折叠</button><button class="retry">翻译此段</button></div><div class="original-text"></div><div id="translation-${p.id}" class="translated-text pending">待翻译</div>`;
  card.querySelector('.original-text').textContent=p.translationSource || p.text;
  card.querySelector('.original-text').hidden=!original;
  card.querySelector('.source-page').onclick=()=>goPage(p.page);
  card.querySelector('.retry').onclick=()=>translateSingle(p,true);
  card.querySelector('.translation-toggle').onclick=()=>setTranslationCollapsed(p,!collapsedTranslations.has(translationFoldKey(p)));
  applyTranslationFold(card,p);
  return card;
}
function renderLayoutPages(container) {
  const generation=bilingualGeneration,documentPdf=pdf;
  const paragraphs=new Map(translationParagraphs().map(p=>[p.id,p]));
  translationImageObserver=new IntersectionObserver(entries=>{
    if(generation!==bilingualGeneration || documentPdf!==pdf)return;
    for(const entry of entries)if(entry.isIntersecting){
      for(const img of entry.target.querySelectorAll('img[data-src]')){img.src=img.dataset.src;delete img.dataset.src;}
      const number=Number(entry.target.dataset.sourcePage);
      if(!sourceTextCache.has(number))sourceTextCache.set(number,sourceTextPage(documentPdf,number));
      sourceTextCache.get(number).then(source=>{
        if(generation!==bilingualGeneration || !entry.target.isConnected)return;
        mountSourceText(entry.target,source,bilingualResizeObserver);drawAnnotations(number);
      }).catch(e=>{
        if(generation!==bilingualGeneration)return;
        sourceTextCache.delete(number);toast(`第 ${number} 页文字层加载失败：${e.message}`,true);
      });
      translationImageObserver.unobserve(entry.target);
    }
  },{root:$('#translation-view'),rootMargin:'1200px 0px'});
  for(const page of translationLayout.data.pages){
    const section=document.createElement('section');section.className='bilingual-page';section.dataset.sourcePage=page.page;
    const heading=document.createElement('div');heading.className='bilingual-page-heading';
    heading.innerHTML=`<span>PAGE ${String(page.page).padStart(2,'0')} <small>${page.manual?'已手动调整':page.twoColumns?'双栏原稿':'原版图文'}</small></span><div class="page-layout-actions"><button class="text-button edit-layout" aria-label="调整第 ${page.page} 页切分">调整切分</button><button class="text-button view-original">查看原页 ↗</button></div>`;
    heading.querySelector('.view-original').onclick=()=>goPage(page.page);heading.querySelector('.edit-layout').onclick=()=>layoutEditor.open(page.page);section.append(heading);
    const sheet=document.createElement('div');sheet.className='bilingual-sheet';section.append(sheet);
    const appendTile=(col,tile)=>{
          const [x0,y0,x1,y1]=tile.displayRect || tile.rect,w=x1-x0,h=y1-y0;
          const crop=document.createElement('div');crop.className='source-crop';crop.style.aspectRatio=`${w} / ${h}`;
          crop.dataset.rect=JSON.stringify(tile.rect);crop.dataset.graphics=String(tile.hasGraphics);
          crop.dataset.displayRect=JSON.stringify(tile.displayRect || tile.rect);
          const img=document.createElement('img');img.dataset.src=`/api/documents/${doc.id}/pages/${page.page}/image`;
          img.decoding='async';img.draggable=false;
          img.alt=`第 ${page.page} 页原版内容${tile.hasGraphics?'（含图表）':''}：`+tile.paragraphIds.map(id=>paragraphs.get(id)?.text||'').join(' ').slice(0,500);
          img.style.cssText=`left:${-x0/w*100}%;top:${-y0/h*100}%;width:${page.width/w*100}%;height:${page.height/h*100}%;`;
          img.onerror=()=>{crop.classList.add('image-error');crop.title='页面图像加载失败，请查看原页或刷新重试。';};
          crop.append(img);col.append(crop);
          const translatedParagraphs=tile.paragraphIds.map(id=>paragraphs.get(id)).filter(p=>p && p.translatable!==false);
          if(translatedParagraphs.length){
            const translations=document.createElement('div');translations.className='layout-translations';
            translations.style.paddingLeft=`${tile.padding[0]*100}%`;translations.style.paddingRight=`${tile.padding[1]*100}%`;
            for(const p of translatedParagraphs)translations.append(paragraphCard(p,false));
            col.append(translations);
          }
    };
    if(page.tree){
      const appendNode=(parent,node)=>{
        const el=document.createElement('div');el.className='manual-layout-node';parent.append(el);
        if(node.tile){appendTile(el,node.tile);return;}
        el.dataset.direction=node.direction;
        if(node.direction==='row')el.style.gridTemplateColumns=node.weights.map(w=>`minmax(0,${w}fr)`).join(' ');
        for(const child of node.children)appendNode(el,child);
      };
      appendNode(sheet,page.tree);
    }else for(const row of page.rows){
      const rowEl=document.createElement('div');rowEl.className='layout-row';rowEl.dataset.columns=row.columns.length;
      for(const column of row.columns){const col=document.createElement('div');col.className='layout-column';for(const tile of column)appendTile(col,tile);rowEl.append(col);}
      sheet.append(rowEl);
    }
    for(const id of page.unplacedIds){const p=paragraphs.get(id);if(p && p.translatable!==false){const card=paragraphCard(p);card.classList.add('layout-unplaced');sheet.append(card);}}
    container.append(section);
    translationImageObserver.observe(section);
  }
}
function renderParagraphs() {
  annotationActions.hide();
  if(!doc)return;
  bilingualGeneration++;translationImageObserver?.disconnect();bilingualResizeObserver.disconnect();
  selection=null;$('#selection-toolbar').hidden=true;
  const container=$('#paragraphs');container.replaceChildren();let lastPage=0;
  const rich=$('#translation-display').value==='layout';
  if(rich && translationLayout.data){
    renderLayoutPages(container);
    $('#translation-display-hint').textContent='页眉、页脚、页码、独立公式和图内文字保留原貌，不翻译；正文与图注逐段翻译，均可选字和批注。';
  }else{
    for(const p of translationParagraphs()) {
      if(p.translatable===false)continue;
      if(lastPage!==p.page){const h=document.createElement('div');h.className='translation-page-label';h.textContent=`PAGE ${String(p.page).padStart(2,'0')}`;container.append(h);lastPage=p.page;}
      container.append(paragraphCard(p));
    }
    if(!translationParagraphs().length)container.innerHTML='<div class="drawer-empty">此文档没有可翻译的文字。可切换原版图文查看，或在「调整切分」中手动补充文字。</div>';
    if(rich && mode==='translation')ensureTranslationLayout();
    else if(!rich)$('#translation-display-hint').textContent='仅显示正文和图注，支持译文批注；页眉页脚、页码、独立公式和图内文字不翻译，可切换「原版图文」查看原貌。';
  }
  for(const p of translationParagraphs())updateParagraph(p);
  updateTranslationProgress();
}
function updateParagraph(p,error='') {
  const el=$(`#para-${p.id} .translated-text`);if(!el)return;
  const text=translationValue(p),oldText=doc.state.translations[translationKey(p)];
  el.textContent=error || text || (oldText?'原段落混有非正文内容，请重新翻译正文。':p.manual?'手动调整段落 · 待翻译':'待翻译');
  if(text&&!error)renderMathInElement(el,{delimiters:[{left:'$$',right:'$$',display:true},{left:'\\[',right:'\\]',display:true},{left:'\\(',right:'\\)',display:false},{left:'$',right:'$',display:false}],throwOnError:false,trust:false,strict:'ignore',maxExpand:1000,maxSize:20});
  el.classList.toggle('pending',!text&&!error);el.classList.toggle('failed',!!error);
  drawTranslationAnnotations(el);bilingualResizeObserver.observe(el);
  $(`#para-${p.id} .retry`).textContent=text?'重新翻译':'翻译此段';
}
function updateTranslationProgress() {
  if(!doc)return;
  const range=translationRange(), paragraphs=rangeParagraphs(range);
  const done=paragraphs.filter(p=>translationValue(p)).length,total=paragraphs.length;
  const skipped=range.valid?translationParagraphs().filter(p=>p.translatable===false && p.page>=range.start && p.page<=range.end).length:0;
  const scope=range.full?'全文':`第 ${range.start}–${range.end} 页`;
  $('#translation-progress').style.width=`${total?done/total*100:0}%`;
  $('#translation-status').textContent=range.valid ? `${$('#target-language').value} · ${scope} · 已完成 ${done} / ${total} 段${translating?' · 正在翻译':''}` : '请检查翻译页码范围';
  $('#translate-all span').textContent=translating ? (pauseTranslation?'正在暂停…':'暂停翻译') : !range.valid ? '翻译所选页' : done===total&&total ? (range.full?'全文翻译已完成':'所选页翻译已完成') : done ? `继续翻译${scope}` : range.full?'一键翻译全文':`翻译${scope}`;
  $('#translate-all').disabled=!translating && (!range.valid || !total || done===total);
  $('#translation-range-hint').textContent=!range.valid ? `请输入 1–${doc.pageCount} 之间的整数，起始页不能大于结束页。` : !total ? (skipped?'所选页面仅含页眉页脚、页码、公式或图内文字，保留原貌，无需翻译。':'所选页面没有可提取的文字，请选择其他页或先进行 OCR。') : `包含起止页，按 PDF 页序计算（共 ${doc.pageCount} 页）。已翻译段落会自动跳过。${skipped?`已排除 ${skipped} 个页眉页脚、公式、图内文字等片段。`:''}`;
  $('#translation-range-hint').classList.toggle('error',!range.valid);
  for(const input of [$('#translation-from'),$('#translation-to')]){input.disabled=translating;input.setAttribute('aria-invalid',String(!range.valid));}
  $('#translation-full').disabled=translating;
  $('#target-language').disabled=translating;
  $$('.retry').forEach(b=>b.disabled=translating);
  $$('.edit-layout').forEach(b=>b.disabled=translating);
}
async function translateParagraph(p,force=false) {
  if(p.translatable===false)return;
  const el=$(`#para-${p.id} .translated-text`);if(el){el.textContent='正在翻译…';el.className='translated-text pending';}
  translationAbort=new AbortController();
  const response=await api(`/api/documents/${doc.id}/translate`,{method:'POST',body:{config:requestConfig(),paragraphId:p.id,language:$('#target-language').value,force},signal:translationAbort.signal});
  if(response.skipped){p.translatable=false;renderParagraphs();return;}
  doc.state.translations[translationKey(p)]=response.text;
  doc.state.translationSources ??= {};doc.state.translationSources[translationKey(p)]=response.sourceHash;
  updateParagraph(p);updateTranslationProgress();
  if(drawer==='annotations')renderDrawer();
}
async function translateSingle(p,force) {
  if(translating || !requireConfig())return;
  translating=true;pauseTranslation=false;updateTranslationProgress();
  try{await translateParagraph(p,force);}catch(e){updateParagraph(p,e.message);toast(e.message,true);}
  finally{translating=false;translationAbort=null;updateTranslationProgress();}
}
async function translateAll() {
  if(translating){pauseTranslation=true;updateTranslationProgress();toast('当前段落完成后暂停，已完成的译文会保留。');return;}
  if(!requireDoc())return;
  const range=translationRange(), paragraphs=rangeParagraphs(range);
  if(!range.valid){updateTranslationProgress();return toast('请填写有效的翻译页码范围。',true);}
  if(!paragraphs.length)return toast('所选页面没有可翻译的文字。');
  if(!requireConfig())return;
  translating=true;pauseTranslation=false;updateTranslationProgress();
  try {
    for(const p of paragraphs) {
      if(pauseTranslation)break;
      if(translationValue(p))continue;
      try{await translateParagraph(p);}catch(e){updateParagraph(p,`翻译失败：${e.message}`);throw e;}
    }
    toast(pauseTranslation?'翻译已暂停，下次可继续。':range.full?'全文翻译已完成。':`第 ${range.start}–${range.end} 页翻译已完成。`);
  }catch(e){toast(e.message+' 已完成的译文已保存，可继续翻译。',true);}
  finally{translating=false;translationAbort=null;updateTranslationProgress();}
}
function exportTranslation() {
  if(!requireDoc())return;
  let text=`# ${doc.title}\n\n目标语言：${$('#target-language').value}\n\n正文与图注双语对照；页眉页脚、页码、独立公式及图内文字保留在原 PDF 中，不重复翻译。\n\n`;
  for(const p of translationParagraphs()){
    const notes=doc.state.annotations.filter(a=>a.source==='translation' && a.paragraphId===p.id && a.language===$('#target-language').value);
    if(p.translatable===false && !notes.length)continue;
    text+=`### 第 ${p.page} 页 · ${p.id}\n\n`;
    if(p.translatable!==false)text+=`${p.translationSource || p.text}\n\n> ${(translationValue(p) || '（未翻译）').replace(/\n/g,'\n> ')}\n\n`;
    else text+='此段属于页眉页脚、页码、公式或图内文字，不再翻译。以下为此前保存的批注。\n\n';
    for(const a of notes){
      text+=`**译文批注 · ${{highlight:'高亮',underline:'下划线',note:'备注'}[a.kind]}${a.translationText!==translationValue(p)?'（译文已更新，以下为旧选文）':''}**\n\n> ${a.text.replace(/\n/g,'\n> ')}\n\n${a.note?`${a.note}\n\n`:''}`;
    }
    text+='---\n\n';
  }
  const activeIds=new Set(translationParagraphs().map(p=>p.id));
  for(const a of doc.state.annotations.filter(a=>a.source==='translation' && !activeIds.has(a.paragraphId) && a.language===$('#target-language').value)){
    text+=`### 第 ${a.page} 页 · 历史译文批注\n\n切分已调整，保留此前的选文和笔记。\n\n> ${a.text.replace(/\n/g,'\n> ')}\n\n${a.note||''}\n\n`;
  }
  download(new Blob([text],{type:'text/markdown;charset=utf-8'}),doc.name.replace(/\.pdf$/i,'')+'-bilingual.md');
}
function download(blob,name) {const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);}

function renderMarkdown(el,text) {
  renderChatMarkdown(el,text);
  const walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT),nodes=[];
  while(walker.nextNode())if(!walker.currentNode.parentElement.closest('code,pre,a,.chat-math'))nodes.push(walker.currentNode);
  for(const node of nodes){if(!/\[p\d+\]/.test(node.textContent))continue;const frag=document.createDocumentFragment();for(const part of node.textContent.split(/(\[p\d+\])/)){const m=part.match(/^\[p(\d+)\]$/);if(m){const b=document.createElement('button');b.className='page-citation';b.textContent=`p.${m[1]}`;b.onclick=()=>goPage(Number(m[1]));frag.append(b);}else frag.append(document.createTextNode(part));}node.replaceWith(frag);}
  el.querySelectorAll('a').forEach(a=>{a.target='_blank';a.rel='noopener noreferrer';});
}
function appendMessage(message) {
  $('#chat-empty')?.remove();const el=document.createElement('div');el.className=`message ${message.role==='user'?'user':'assistant-message'}`;
  el.innerHTML=`<div class="role">${message.role==='user'?'你':icon('spark')+'阅读助手'}</div><div class="content"></div>`;
  if(message.role==='user')el.querySelector('.content').textContent=message.content;else renderMarkdown(el.querySelector('.content'),message.content);
  if(message.role==='user')appendMessageImages(el,message.attachments,doc.id);
  $('#messages').append(el);return el;
}
function renderMessages() {
  $('#messages').innerHTML='';
  if(!doc?.state.messages.length) {$('#messages').innerHTML=initialChat;wireSuggestions();return;}
  doc.state.messages.forEach(appendMessage);$('#messages').scrollTop=$('#messages').scrollHeight;
}
function wireSuggestions() {$$('[data-prompt]').forEach(b=>b.onclick=()=>{$('#question').value=t(b.dataset.prompt);$('#question').focus();});}
async function sendChat(e) {
  e?.preventDefault();
  if(chatBusy || !requireDoc() || !requireConfig())return;
  const question=$('#question').value.trim() || (chatImages.items.length?t('请结合论文解释这些图片。'):'');if(!question)return;
  if(chatImages.preparing)return toast('图片正在读取，请稍后发送。');
  if(!doc.paragraphs.length && !chatImages.items.length && !doc.state.messages.some(m=>m.attachments?.length))return toast('未提取到原文文字，请先对扫描 PDF 进行 OCR，或添加图片提问。',true);
  const chatConfig=requestConfig();
  let attachments=[];chatBusy=true;chatImages.render();$('#send').disabled=true;$('#clear-chat').disabled=true;$('#question').readOnly=true;
  try {attachments=await chatImages.upload(doc.id);}
  catch(error){chatBusy=false;chatImages.render();$('#send').disabled=false;$('#clear-chat').disabled=false;$('#question').readOnly=false;toast(error.message,true);return;}
  $('#send').disabled=false;$('#question').readOnly=false;
  const selected=quotedText,displayQuestion=selected?`${question}\n\n引用原文：${selected}`:question;
  if(retryDraft?.documentId===doc.id && doc.state.messages.at(-1)===retryDraft.user){doc.state.messages.pop();renderMessages();}
  retryDraft=null;
  const user={role:'user',content:displayQuestion,...(attachments.length?{attachments}:{})};doc.state.messages.push(user);appendMessage(user);$('#question').value='';setQuote('');chatImages.clear();
  saveState({messages:doc.state.messages.slice()});
  const history=doc.state.messages.slice();const answer={role:'assistant',content:''},node=appendMessage(answer),content=node.querySelector('.content');
  content.textContent=t('正在阅读与思考…');chatBusy=true;chatAbort=new AbortController();$('#send').hidden=true;$('#stop-chat').hidden=false;$('#clear-chat').disabled=true;
  const scroll=()=>{$('#messages').scrollTop=$('#messages').scrollHeight;};scroll();
  let lastRender=0, ended=false;
  try {
    const response=await fetch(`/api/documents/${doc.id}/chat`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({config:chatConfig,messages:history,selection:selected}),signal:chatAbort.signal});
    if(!response.ok){const error=await response.json();throw new Error(error.error || '请求失败');}
    const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='';
    const consume=payload=>{
      if(!payload.startsWith('data:'))return;
      const data=JSON.parse(payload.slice(5));
      if(data.error)throw new Error(data.error);
      if(data.context)$('#context-status').innerHTML=icon('file')+data.context;
      if(data.text){answer.content+=data.text;if(Date.now()-lastRender>90){renderMarkdown(content,answer.content);lastRender=Date.now();scroll();}}
      if(data.done)ended=true;
    };
    while(true){const {value,done}=await reader.read();buffer+=decoder.decode(value || new Uint8Array(),{stream:!done});let index;while((index=buffer.indexOf('\n\n'))>=0){consume(buffer.slice(0,index));buffer=buffer.slice(index+2);}if(done)break;}
    if(!ended)throw new Error('连接中断，已保留收到的内容。');
  }catch(error){const message=error.name==='AbortError'?'已停止生成。':error.message;const notice=document.createElement('div');notice.className='message-error';notice.textContent=message;node.append(notice);
    if(!answer.content){const retry=document.createElement('button');retry.type='button';retry.className='text-button chat-retry';retry.textContent='重新编辑问题';const sourceId=doc.id;retry.onclick=()=>{if(chatBusy || doc?.id!==sourceId)return;retryDraft={documentId:sourceId,user};$('#question').value=question;setQuote(selected);chatImages.restore(attachments,sourceId);$('#question').focus();};node.append(retry);}
  }
  finally {
    if(answer.content){renderMarkdown(content,answer.content);doc.state.messages.push(answer);}else content.textContent=t('未收到回答。检查设置后可重新提问。');
    chatBusy=false;chatAbort=null;chatImages.render();$('#send').hidden=false;$('#stop-chat').hidden=true;$('#clear-chat').disabled=false;await saveState({messages:doc.state.messages});scroll();
  }
}
function openSettings() {
  $('#model-options').hidePopover();
  $('#api-url').value=config.baseUrl;$('#api-model').value=config.model;$('#api-key').value=config.apiKey;$('#remember-key').checked=config.rememberKey;
  $('#api-display-name').value=config.displayName;$('#api-reasoning').value=config.reasoningEffort;
  apiModelPicker.reset();
  $('#connection-result').textContent='';$('#api-key').type='password';$('#toggle-key').textContent='显示';$('#settings-dialog').showModal();
  libraryUI.loadStorage();
}
function settingsValues(){return{...config,baseUrl:$('#api-url').value.trim().replace(/\/+$/,''),displayName:$('#api-display-name').value.trim(),model:$('#api-model').value.trim(),reasoningEffort:$('#api-reasoning').value,apiKey:$('#api-key').value.trim(),rememberKey:$('#remember-key').checked};}
function requestConfig(value=config){return{baseUrl:value.baseUrl,model:value.model,reasoningEffort:value.reasoningEffort,apiKey:value.apiKey,uiLanguage:getLocale()};}
function recentModels(){return [...new Set([config.model,...config.recentModels].filter(Boolean))].slice(0,12);}
function saveConfig(value){
  if(!value.model){toast('请填写实际模型 ID。',true);return false;}
  const next={...value,recentModels:[...new Set([value.model,...recentModels()])].slice(0,12)};
  try{localStorage.setItem('paperdesk.config',JSON.stringify({...next,apiKey:next.rememberKey?next.apiKey:''}));}
  catch{toast('设置未保存：浏览器存储不可用，请检查后重试。',true);return false;}
  config=next;apiModelPicker.reset();quickModelPicker.reset();modelStatus();return true;
}
function modelStatus(){
  const ready=!!(config.baseUrl&&config.model),name=config.displayName||config.model;
  $('#model-status').classList.toggle('configured',ready);
  $('#model-status span:nth-child(2)').textContent=ready?name:'配置你的 AI 模型';
  $('#model-status').title=ready?`${name}\n实际模型：${config.model}\n思考强度：${reasoningLabels[config.reasoningEffort]}`:'配置 AI 连接';
  $('#model-options-toggle').title=`模型：${config.model||'尚未设置'}\n思考强度：${reasoningLabels[config.reasoningEffort]}`;
  $('#model-options-toggle').classList.toggle('has-effort',config.reasoningEffort!=='default');
}
function positionModelOptions(){
  const panel=$('#model-options');if(!panel.matches(':popover-open'))return;
  const anchor=$('#model-options-toggle').getBoundingClientRect();
  panel.style.left=`${Math.max(16,Math.min(anchor.left,window.innerWidth-panel.offsetWidth-16))}px`;
  panel.style.top=`${Math.max(16,Math.min(anchor.top-panel.offsetHeight-12,window.innerHeight-panel.offsetHeight-16))}px`;
}
const apiModelPicker=new ModelPicker({root:$('#api-model-picker'),getConnection:settingsValues,getRecent:()=>settingsValues().baseUrl===config.baseUrl?recentModels():[]});
const quickModelPicker=new ModelPicker({root:$('#quick-model-picker'),getConnection:()=>config,getRecent:recentModels,onResize:positionModelOptions});
$('#api-url').addEventListener('input',()=>apiModelPicker.reset());
$('#api-key').addEventListener('input',()=>apiModelPicker.reset());
$('#settings-dialog').addEventListener('close',()=>apiModelPicker.reset());
$('#model-options').addEventListener('beforetoggle',e=>{
  if(e.newState!=='open'){quickModelPicker.reset();return;}
  $('#quick-model').value=config.model;$('#quick-reasoning').value=config.reasoningEffort;
  quickModelPicker.reset();
  $('#model-options-connection').textContent=config.displayName||config.model||'当前连接尚未配置';
});
$('#model-options').addEventListener('toggle',e=>{
  if(e.newState==='open'){positionModelOptions();$('#quick-model').focus();}
});
$('#model-options-toggle').onclick=e=>{
  e.preventDefault();$('#model-options').togglePopover();positionModelOptions();
};
window.addEventListener('resize',positionModelOptions);
new ResizeObserver(positionModelOptions).observe($('.assistant'));
$('#model-options-form').onsubmit=e=>{
  e.preventDefault();
  if(!saveConfig({...config,model:$('#quick-model').value.trim(),reasoningEffort:$('#quick-reasoning').value}))return;
  $('#model-options').hidePopover();$('#model-options-toggle').focus();toast('模型设置已保存，将用于后续问答和翻译。');
};
$('#model-connection-settings').onclick=openSettings;

$('#import').onclick=$('#welcome-import').onclick=()=>$('#file-input').click();
$('#file-input').onchange=e=>importFile(e.target.files[0]);
$('#open-sample').onclick=async()=>{try{const r=await fetch('/static/sample.pdf');if(!r.ok)throw new Error('示例文件不可用');await importFile(new File([await r.blob()],'Ai4PDF — A Reading Companion.pdf',{type:'application/pdf'}));}catch(e){toast(e.message,true);}};
$('#pdf-tab').onclick=()=>switchMode('pdf');$('#translation-tab').onclick=()=>switchMode('translation');
$('#prev').onclick=()=>goPage(currentPage-1);$('#next').onclick=()=>goPage(currentPage+1);$('#page-number').onchange=e=>goPage(e.target.value);
$('#zoom').onchange=()=>buildPages().catch(e=>toast(e.message,true));$('#pdf-scroll').onscroll=onScroll;
$('#pages').addEventListener('mouseup',()=>setTimeout(captureSelection,10));
$('#paragraphs').addEventListener('mouseup',()=>setTimeout(captureSelection,10));
$('#paragraphs').addEventListener('copy',e=>{
  const selected=window.getSelection();if(!selected?.rangeCount || selected.isCollapsed)return;
  const range=selected.getRangeAt(0),node=range.commonAncestorContainer;
  const el=(node.nodeType===1?node:node.parentElement).closest('.translated-text');
  if(!el || !e.clipboardData)return;
  const anchor=selectedTextAnchor(el,range);if(!anchor)return;
  // KaTeX includes a hidden accessibility representation. Copy visible text once.
  e.clipboardData.setData('text/plain',anchor.text);e.preventDefault();
});
for(const el of [$('#pages'),$('#paragraphs')])el.addEventListener('keyup',e=>{if(e.shiftKey)captureSelection();});
$('#translation-view').addEventListener('scroll',()=>$('#selection-toolbar').hidden=true);
$('#paragraphs').addEventListener('scroll',e=>{const el=e.target.closest('.translated-text');if(el)drawTranslationAnnotations(el);},true);
$('#selection-toolbar').onmousedown=e=>{if(e.target.tagName!=='SELECT')e.preventDefault();};
$('#highlight-selection').onclick=()=>addAnnotation('highlight');$('#underline-selection').onclick=()=>addAnnotation('underline');$('#note-selection').onclick=()=>openNote();
$('#ask-selection').onclick=()=>{if(!selection)return;setQuote(selection.text);$('#selection-toolbar').hidden=true;$('#question').focus();$('#question').value=t('请解释这段文字的含义。');$('.assistant').scrollIntoView({block:'nearest'});};
$('#clear-selection').onclick=()=>setQuote('');
$('#note-form').onsubmit=async e=>{e.preventDefault();try{if(annotationEdit){await api(`/api/documents/${doc.id}/annotations/${annotationEdit.id}`,{method:'PATCH',body:{note:$('#note-text').value}});annotationEdit.note=$('#note-text').value;drawAnnotations(annotationEdit.page);renderDrawer();}else if(!await addAnnotation('highlight',$('#note-text').value))return;$('#note-dialog').close();}catch(error){toast(error.message,true);}};
$$('[data-drawer]').forEach(b=>b.onclick=()=>toggleDrawer(b.dataset.drawer).catch(e=>toast(e.message,true)));$('#close-drawer').onclick=closeDrawer;
$('#settings').onclick=$('#model-status').onclick=openSettings;
$$('.close-dialog').forEach(b=>b.onclick=()=>b.closest('dialog').close());
$('#toggle-key').onclick=()=>{const input=$('#api-key');input.type=input.type==='password'?'text':'password';$('#toggle-key').textContent=input.type==='password'?'显示':'隐藏';};
$('#settings-form').onsubmit=e=>{e.preventDefault();if(!saveConfig(settingsValues()))return;$('#settings-dialog').close();toast('API 设置已保存。');};
$('#test-connection').onclick=async()=>{if(!$('#settings-form').reportValidity())return;const result=$('#connection-result');result.className='connection-result';result.textContent='正在连接…';$('#test-connection').disabled=true;try{const r=await api('/api/test',{method:'POST',body:{config:requestConfig(settingsValues())}});result.textContent='连接成功 · '+r.message;}catch(e){result.textContent=e.message;result.classList.add('error');}finally{$('#test-connection').disabled=false;}};
$('#chat-form').onsubmit=sendChat;$('#question').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();sendChat();}};
$('#stop-chat').onclick=()=>chatAbort?.abort();$('#clear-chat').onclick=()=>{if(!requireDoc()||chatBusy)return;if(doc.state.messages.length&&!confirm(t('清空这份文档的对话记录？')))return;doc.state.messages=[];chatImages.clear();retryDraft=null;$('#question').value='';setQuote('');renderMessages();saveState({messages:[]});};
$('#translate-all').onclick=translateAll;$('#target-language').onchange=()=>{try{localStorage.setItem('paperdesk.translationLanguage',$('#target-language').value);}catch{}renderParagraphs();};$('#export-translation').onclick=exportTranslation;
$('#translation-from').oninput=$('#translation-to').oninput=changeTranslationRange;
$('#translation-full').onclick=()=>{if(!doc||translating)return;$('#translation-from').value=1;$('#translation-to').value=doc.pageCount;changeTranslationRange();};
$('#translation-display').onchange=()=>{localStorage.setItem('paperdesk.display',$('#translation-display').value);translationLayout.error=false;renderParagraphs();};
$('#export').onclick=async()=>{if(!requireDoc())return;$('#export').disabled=true;try{const r=await fetch(`/api/documents/${doc.id}/export`);if(!r.ok){const e=await r.json();throw new Error(e.error);}download(await r.blob(),doc.name.replace(/\.pdf$/i,'')+'-annotated.pdf');toast('已导出带原生批注的 PDF，原文件保持不变。');}catch(e){toast(e.message,true);}finally{$('#export').disabled=false;}};
let dragDepth=0;
document.addEventListener('dragenter',e=>{if(e.dataTransfer.types.includes('Files')){e.preventDefault();if([...e.dataTransfer.items].some(item=>item.type.startsWith('image/')))return;dragDepth++;$('#drop-overlay').hidden=false;}});
document.addEventListener('dragleave',()=>{if(--dragDepth<=0){dragDepth=0;$('#drop-overlay').hidden=true;}});
document.addEventListener('dragover',e=>{if(e.dataTransfer.types.includes('Files'))e.preventDefault();});
document.addEventListener('drop',e=>{e.preventDefault();dragDepth=0;$('#drop-overlay').hidden=true;const files=[...e.dataTransfer.files];if(files.some(file=>file.type.startsWith('image/')))return toast('请把图片拖到右侧 AI 助手中。');importFile(files[0]);});
let resizing=false;
$('#resizer').onpointerdown=e=>{resizing=true;$('#resizer').setPointerCapture(e.pointerId);document.body.style.userSelect='none';};
$('#resizer').onpointermove=e=>{if(resizing)document.documentElement.style.setProperty('--assistant-width',`${Math.max(300,Math.min(window.innerWidth*.55,window.innerWidth-e.clientX))}px`);};
$('#resizer').onpointerup=()=>{resizing=false;document.body.style.userSelect='';if(doc&&$('#zoom').value==='fit')buildPages().catch(e=>toast(e.message,true));};
$('#resizer').onkeydown=e=>{if(['ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();const width=$('.assistant').offsetWidth+(e.key==='ArrowLeft'?20:-20);document.documentElement.style.setProperty('--assistant-width',`${Math.max(300,Math.min(window.innerWidth*.55,width))}px`);if(doc&&$('#zoom').value==='fit')buildPages();}};
window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{if(doc&&mode==='pdf'&&$('#zoom').value==='fit')buildPages().catch(e=>toast(e.message,true));},300);});
window.addEventListener('beforeunload',e=>{if(chatBusy||translating){e.preventDefault();e.returnValue='';}});
document.addEventListener('keydown',e=>{if(e.key==='Escape')$('#selection-toolbar').hidden=true;});
wireSuggestions();modelStatus();
$('#system-language').value=getLocale();
$('#system-language').onchange=()=>{
  try{setLocale($('#system-language').value);positionModelOptions();}
  catch{ $('#system-language').value=getLocale();toast('设置未保存：浏览器存储不可用，请检查后重试。',true); }
};
try{const target=localStorage.getItem('paperdesk.translationLanguage');if([...$('#target-language').options].some(option=>option.value===target))$('#target-language').value=target;}catch{}
startI18n();
$('#translation-display').value=localStorage.getItem('paperdesk.display')==='text'?'text':'layout';
const last=localStorage.getItem('paperdesk.last');if(last)openById(last);
