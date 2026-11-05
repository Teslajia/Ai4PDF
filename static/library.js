import { t, getLocale } from './i18n.js';

const $=selector=>document.querySelector(selector);
const esc=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const user=value=>`<span data-user-content>${esc(value)}</span>`;
const tagsFrom=value=>[...new Set(value.split(/[,，\n]/).map(s=>s.trim()).filter(Boolean))];
const size=value=>value>=1024**3?`${(value/1024**3).toFixed(1)} GB`:`${(value/1024**2).toFixed(1)} MB`;

export class LibraryUI {
  constructor({api,notify,busy,flush,onChange,openDocument}){
    Object.assign(this,{api,notify,busy,flush,onChange,openDocument});
    this.documents=[];this.folders=[];this.selection=new Set();this.filter='all';this.pending=false;this.migrating=false;
    const node=document.createElement('div');
    node.innerHTML=`<dialog id="library-dialog" aria-labelledby="library-title">
      <div class="dialog-heading"><div><div class="eyebrow">YOUR RESEARCH, ORGANIZED</div><h2 id="library-title">管理文档库</h2></div><button type="button" class="icon-button" id="library-close" aria-label="关闭文档库">×</button></div>
      <p class="library-intro">整理文档、文件夹和标签。删除的文档可从回收站恢复。</p>
      <p id="library-error" class="library-error" role="alert" hidden></p>
      <div class="library-workspace"><aside class="library-nav"><nav id="library-folders" aria-label="文档库文件夹"></nav>
        <button type="button" id="library-folder-add" class="text-button">＋ 新建文件夹</button>
        <div id="library-folder-actions" hidden><button type="button" id="library-folder-rename" class="text-button">重命名文件夹</button><button type="button" id="library-folder-delete" class="text-button">删除文件夹</button></div>
      </aside><section class="library-main">
        <div class="library-filters"><input type="search" id="library-search" placeholder="搜索标题、文件名或标签" aria-label="搜索文档库"><select id="library-tag-filter" aria-label="按标签筛选"></select><select id="library-sort" aria-label="文档排序"><option value="newest">最近导入</option><option value="title">按标题排序</option></select></div>
        <div class="library-selection"><label><input type="checkbox" id="library-select-all">全选当前列表</label><span id="library-count" aria-live="polite"></span><button type="button" class="text-button" id="library-refresh">刷新</button></div>
        <div id="library-batch" class="library-batch" hidden><span id="library-selected"></span><button type="button" class="button" data-batch="move">移动到文件夹</button><button type="button" class="button" data-batch="addTags">添加标签</button><button type="button" class="button" data-batch="removeTags">移除标签</button><button type="button" class="button danger" data-batch="trash">移入回收站</button><button type="button" class="button" data-batch="restore">恢复</button><button type="button" class="button danger" data-batch="purge">彻底删除</button></div>
        <div id="library-documents" class="library-documents"></div>
      </section></div></dialog>
      <dialog id="library-editor" aria-labelledby="library-editor-title"><form id="library-edit-form"><div class="dialog-heading"><h2 id="library-editor-title">编辑文档</h2><button type="button" class="icon-button" id="library-editor-close" aria-label="关闭">×</button></div>
        <label id="library-title-field">文档标题<input id="library-doc-title" maxlength="300"></label>
        <label id="library-folder-field">文件夹<select id="library-doc-folder"></select></label>
        <label id="library-tags-field">标签<input id="library-doc-tags" maxlength="1230" placeholder="用逗号分隔，例如：超分辨率, 待读"><small>每份文档最多 30 个标签，每个标签最多 40 个字符。</small></label>
        <div id="library-edit-error" class="library-error" role="alert" hidden></div><div class="dialog-actions"><button type="button" id="library-edit-cancel" class="button">取消</button><button type="submit" class="button primary" id="library-edit-save">保存</button></div></form></dialog>`;
    document.body.append(node);
    $('#library-close').onclick=()=>$('#library-dialog').close();
    $('#library-editor-close').onclick=$('#library-edit-cancel').onclick=()=>$('#library-editor').close();
    $('#library-search').oninput=()=>{this.selection.clear();this.renderList();};
    $('#library-tag-filter').onchange=$('#library-sort').onchange=()=>{this.selection.clear();this.renderList();};
    $('#library-select-all').onchange=e=>{this.selection=new Set(e.target.checked?this.visible().map(d=>d.id):[]);this.renderList();};
    $('#library-refresh').onclick=()=>this.refresh().catch(e=>this.error(e));
    $('#library-folder-add').onclick=()=>this.changeFolder('create');
    $('#library-folder-rename').onclick=()=>this.changeFolder('rename');
    $('#library-folder-delete').onclick=()=>this.changeFolder('delete');
    $('#library-batch').onclick=e=>{const b=e.target.closest('[data-batch]');if(b)this.action(b.dataset.batch,[...this.selection]);};
    $('#library-edit-form').onsubmit=e=>{e.preventDefault();this.saveEdit();};
    $('#library-open-settings').onclick=()=>{ $('#settings-dialog').close();this.open(); };
    $('#library-migrate').onclick=()=>this.startMigration();
    $('#library-copy-path').onclick=()=>navigator.clipboard.writeText(this.storage?.path||'').then(()=>this.notify('路径已复制。')).catch(()=>{ $('#library-current-path').focus();$('#library-current-path').select(); });
    for(const id of ['library-dialog','library-editor'])$( `#${id}`).addEventListener('cancel',e=>{if(this.pending)e.preventDefault();});
  }
  error(e){const el=$('#library-error');el.textContent=t(e.message);el.hidden=false;}
  async open(){
    if(!$('#library-dialog').open)$('#library-dialog').showModal();
    try{await this.refresh();}catch(e){this.error(e);}
  }
  async refresh(){
    const data=await this.api('/api/library');this.documents=data.documents;this.folders=data.folders;
    if(!['all','unfiled','trash'].includes(this.filter)&&!this.folders.some(f=>f.id===this.filter))this.filter='all';
    this.selection.clear();this.render();
  }
  async prepare(){
    if(this.pending||this.migrating)throw new Error('文档库正在处理，请稍后操作。');
    if(this.busy())throw new Error('请先停止问答或翻译，再管理文档库。');
    await this.flush();
  }
  setPending(value){
    this.pending=value;
    for(const control of document.querySelectorAll('#library-dialog button,#library-dialog input,#library-dialog select,#library-editor button,#library-editor input,#library-editor select'))control.disabled=value;
    if(!value&&this.filter==='trash')document.querySelectorAll('.library-doc-open').forEach(b=>b.disabled=true);
  }
  render(){
    const active=this.documents.filter(d=>!d.deletedAt),trash=this.documents.filter(d=>d.deletedAt);
    const entries=[['all','全部文档',active.length],['unfiled','未分类',active.filter(d=>!d.folderId).length],...this.folders.map(f=>[f.id,f.name,active.filter(d=>d.folderId===f.id).length]),['trash','回收站',trash.length]];
    $('#library-folders').innerHTML=entries.map(([id,name,count])=>`<button type="button" data-folder="${esc(id)}" class="library-folder${this.filter===id?' active':''}" aria-current="${this.filter===id?'true':'false'}"><span ${['all','unfiled','trash'].includes(id)?'':'data-user-content'}>${esc(name)}</span><small>${count}</small></button>`).join('');
    $('#library-folders').onclick=e=>{const button=e.target.closest('[data-folder]');if(!button)return;this.filter=button.dataset.folder;this.selection.clear();this.render();};
    $('#library-folder-actions').hidden=['all','unfiled','trash'].includes(this.filter);
    const select=$('#library-tag-filter'),previous=select.value;
    select.innerHTML='<option value="">全部标签</option>'+[...new Set((this.filter==='trash'?trash:active).flatMap(d=>d.tags))].sort().map(tag=>`<option data-user-content value="${esc(tag)}">${esc(tag)}</option>`).join('');
    if([...select.options].some(o=>o.value===previous))select.value=previous;
    this.renderList();
  }
  visible(){
    const search=$('#library-search').value.trim().toLocaleLowerCase(),tag=$('#library-tag-filter').value;
    const docs=this.documents.filter(d=>{
      if(Boolean(d.deletedAt)!==(this.filter==='trash'))return false;
      if(this.filter==='unfiled'&&d.folderId)return false;
      if(!['all','unfiled','trash'].includes(this.filter)&&d.folderId!==this.filter)return false;
      return (!tag||d.tags.includes(tag))&&(!search||[d.title,d.name,...d.tags].join(' ').toLocaleLowerCase().includes(search));
    });
    if($('#library-sort').value==='title')docs.sort((a,b)=>a.title.localeCompare(b.title,getLocale()));
    return docs;
  }
  renderList(){
    const docs=this.visible(),trash=this.filter==='trash';
    $('#library-count').textContent=t(`${docs.length} 份文档`);
    $('#library-documents').innerHTML=docs.length?docs.map(d=>{
      const folder=this.folders.find(f=>f.id===d.folderId);
      return `<article class="library-card" data-id="${d.id}"><input type="checkbox" class="library-check" aria-label="${esc(t('选择文档'))}" ${this.selection.has(d.id)?'checked':''}><div class="library-card-body"><button type="button" class="library-doc-open" data-user-content ${trash?'disabled':''}>${esc(d.title)}</button><div class="library-card-meta">${user(d.name)}<span>${d.pageCount} 页</span><span>${new Date(d.created).toLocaleDateString(getLocale())}</span></div><div class="library-card-tags">${folder?`<span class="library-folder-chip" data-user-content>${esc(folder.name)}</span>`:'<span class="library-folder-chip">未分类</span>'}${d.tags.map(tag=>`<span class="library-tag" data-user-content>${esc(tag)}</span>`).join('')}</div></div><div class="library-card-actions">${trash?'<button type="button" class="text-button" data-action="restore">恢复</button><button type="button" class="text-button danger" data-action="purge">彻底删除</button>':'<button type="button" class="text-button" data-action="edit">编辑</button><button type="button" class="text-button danger" data-action="trash">删除</button>'}</div></article>`;
    }).join(''):'<div class="library-empty">没有符合条件的文档。</div>';
    $('#library-documents').onclick=e=>{
      const row=e.target.closest('[data-id]');if(!row)return;const id=row.dataset.id;
      if(e.target.matches('.library-check')){e.target.checked?this.selection.add(id):this.selection.delete(id);this.renderSelection();return;}
      if(e.target.closest('.library-doc-open')){if(this.busy())return this.error(new Error('请先停止问答或翻译，再管理文档库。'));$('#library-dialog').close();this.openDocument(id);return;}
      const button=e.target.closest('[data-action]');if(button)this.action(button.dataset.action,[id]);
    };
    this.renderSelection();
  }
  renderSelection(){
    const count=this.selection.size,visible=this.visible().length,trash=this.filter==='trash';
    $('#library-select-all').checked=visible>0&&count===visible;$('#library-select-all').indeterminate=count>0&&count<visible;
    $('#library-batch').hidden=!count;$('#library-selected').textContent=t(`已选择 ${count} 份`);
    document.querySelectorAll('[data-batch]').forEach(b=>b.hidden=trash?!['restore','purge'].includes(b.dataset.batch):['restore','purge'].includes(b.dataset.batch));
  }
  async changeFolder(action){
    try{
      await this.prepare();const folder=this.folders.find(f=>f.id===this.filter);let name;
      if(action==='delete'){if(!confirm(t('删除此文件夹？其中的文档会移到「未分类」，不会删除文档。')))return;}
      else{name=prompt(t(action==='create'?'新文件夹名称':'重命名文件夹'),folder&&action==='rename'?folder.name:'');if(name===null)return;if(!name.trim())throw new Error('请填写文件夹名称。');}
      this.setPending(true);
      const result=await this.api(action==='create'?'/api/library/folders':`/api/library/folders/${folder.id}`,{method:action==='create'?'POST':action==='delete'?'DELETE':'PATCH',body:action==='delete'?undefined:{name}});
      if(action==='create')this.filter=result.id;
      await this.refresh();await this.onChange(this.documents);
    }catch(e){this.error(e);}finally{this.setPending(false);}
  }
  async action(action,ids){
    try{
      await this.prepare();$('#library-error').hidden=true;
      if(['edit','move','addTags','removeTags'].includes(action)){this.edit(action,ids);return;}
      const question=action==='purge'?`彻底删除这 ${ids.length} 份文档及其批注、译文、对话和图片？此操作无法恢复。`:action==='trash'?`将这 ${ids.length} 份文档移入回收站？可以稍后恢复。`:null;
      if(question&&!confirm(t(question)))return;
      await this.perform(action,ids);
    }catch(e){this.error(e);}
  }
  edit(action,ids){
    this.editing={action,ids};const d=this.documents.find(d=>d.id===ids[0]);
    $('#library-editor-title').textContent={edit:'编辑文档',move:'移动到文件夹',addTags:'添加标签',removeTags:'移除标签'}[action];
    $('#library-title-field').hidden=action!=='edit';$('#library-doc-title').required=action==='edit';$('#library-doc-title').value=d.title;
    $('#library-folder-field').hidden=!['move','edit'].includes(action);
    $('#library-doc-folder').innerHTML='<option value="">未分类</option>'+this.folders.map(f=>`<option data-user-content value="${f.id}">${esc(f.name)}</option>`).join('');
    $('#library-doc-folder').value=d.folderId;
    $('#library-tags-field').hidden=action==='move';$('#library-doc-tags').value=action==='edit'?d.tags.join(', '):'';
    $('#library-edit-error').hidden=true;$('#library-editor').showModal();
  }
  async saveEdit(){
    try{
      await this.prepare();
      const {action,ids}=this.editing;
      await this.perform(action,ids,{title:$('#library-doc-title').value,folderId:$('#library-doc-folder').value,tags:tagsFrom($('#library-doc-tags').value)});
      $('#library-editor').close();
    }catch(e){$('#library-edit-error').textContent=t(e.message);$('#library-edit-error').hidden=false;}
  }
  async perform(action,ids,fields={}){
    this.setPending(true);
    try{
      await this.api('/api/library/batch',{method:'POST',body:{action,ids,...fields}});
      await this.refresh();await this.onChange(this.documents);this.notify('文档库已更新。');
    }catch(e){await this.refresh().catch(()=>{});await this.onChange(this.documents);throw e;}
    finally{this.setPending(false);}
  }
  async loadStorage(){
    try{
      const job=await this.api('/api/library/migration');
      if(job.status==='running'){this.migrating=true;this.pollMigration();return;}
      this.storage=await this.api('/api/library/storage');
      $('#library-current-path').value=this.storage.path;
      $('#library-storage-count').textContent=t(`${this.storage.documents} 份文档 · 回收站 ${this.storage.trash} 份`);
      $('#library-migrate').disabled=this.storage.managedByEnvironment;
      $('#library-environment').hidden=!this.storage.managedByEnvironment;
    }catch(e){$('#library-storage-count').textContent=t(e.message);}
  }
  async startMigration(){
    try{
      await this.prepare();if(!this.storage)throw new Error('请重新打开设置后重试。');
      const target=$('#library-new-path').value.trim();if(!target)throw new Error('请填写新的文档库绝对路径。');
      if(!confirm(t('将全部文档及记录复制到新目录并切换？原目录会保留为备份，迁移期间请保持服务运行。')))return;
      this.migrating=true;$('#library-migrate').disabled=true;$('#library-new-path').disabled=true;
      await this.api('/api/library/migration',{method:'POST',body:{source:this.storage.path,target}});
      this.pollMigration();
    }catch(e){this.migrating=false;$('#library-migrate').disabled=false;$('#library-new-path').disabled=false;this.migrationMessage(e.message,true);}
  }
  migrationMessage(message,error=false){const node=$('#library-migration-status');node.textContent=t(message);node.classList.toggle('error',error);}
  async pollMigration(){
    clearTimeout(this.pollTimer);
    try{
      const job=await this.api('/api/library/migration');
      if(job.status==='running'){
        this.migrating=true;$('#library-migrate').disabled=true;$('#library-new-path').disabled=true;
        this.migrationMessage(`正在复制并校验：${job.completedFiles || 0}/${job.files || 0} 个文件 · ${size(job.copied||0)}`);
        $('#library-migration-progress').hidden=false;$('#library-migration-progress').value=job.total?Math.min(.99,job.copied/job.total):0;
        this.pollTimer=setTimeout(()=>this.pollMigration(),800);return;
      }
      this.migrating=false;$('#library-new-path').disabled=false;$('#library-migration-progress').hidden=true;
      this.migrationMessage(job.status==='done'?'迁移完成，新位置已生效。原目录保留为备份。':job.error||'尚未开始迁移。',job.status==='error');
      if(job.status==='error')$('#library-migration-detail').textContent=t('失败时原文档库不变；目标目录可能保留部分副本，请检查后使用空目录重试。');
      else $('#library-migration-detail').textContent='';
      await this.loadStorage();
    }catch(e){this.migrationMessage('暂时无法获取迁移进度，正在重试。',true);this.pollTimer=setTimeout(()=>this.pollMigration(),2000);}
  }
}
