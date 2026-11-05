const clone=value=>structuredClone(value);
const centerIn=(line,rect)=>{const a=line.rect,x=(a[0]+a[2])/2,y=(a[1]+a[3])/2;return rect[0]<=x&&x<rect[2]&&rect[1]<=y&&y<rect[3];};
const normalize=text=>text.replace(/(\w)-\s*\n(\w)/g,'$1$2').replace(/\s+/g,' ').trim();

export class LayoutEditor {
  constructor({api,notify,documentId,busy,onSave}){
    Object.assign(this,{api,notify,documentId,busy,onSave});
    this.dialog=document.createElement('dialog');this.dialog.id='layout-editor';this.dialog.className='layout-editor';
    this.dialog.innerHTML=`<div class="layout-editor-heading"><div><div class="eyebrow">REFINE THE READING FLOW</div><h2>手动调整切分 · 第 <span id="layout-edit-page"></span> 页</h2></div><button type="button" class="icon-button layout-edit-close" aria-label="关闭切分编辑">×</button></div>
      <div class="layout-edit-tools" role="toolbar" aria-label="切分工具"><button data-mode="select" type="button">选择</button><button data-mode="horizontal" type="button">横向切分</button><button data-mode="vertical" type="button">纵向切分</button><button data-mode="merge" type="button">多选合并</button><button id="layout-select-all" type="button">全选</button><button id="layout-merge" type="button" disabled>合并所选</button><span class="separator"></span><button id="layout-undo" type="button">撤销</button><button id="layout-redo" type="button">重做</button><button id="layout-reset" type="button">恢复自动</button></div>
      <p id="layout-edit-help" class="layout-edit-help"></p><p id="layout-edit-error" role="alert" hidden></p><div class="layout-edit-body"><div class="layout-edit-scroll"><div class="layout-edit-board"><img alt="原页切分预览" draggable="false"><div class="layout-edit-blocks"></div><div class="layout-cut-line" hidden></div></div></div>
      <aside class="layout-edit-details"><h3 id="layout-block-title">选择原文块</h3><p class="layout-edit-small">横切和纵切：选择工具后，在原页空白处点击。合并：选择相邻块，再点「合并所选」。</p><div class="layout-cut-position"><label>块内切分位置 <input id="layout-cut-percent" type="number" min="1" max="99" value="50"> %</label><button id="layout-cut-apply" class="text-button" type="button">按位置切分</button></div><label class="checkbox-label"><input id="layout-block-skip" type="checkbox"> 此块不翻译（公式 / 图片等）</label><label class="layout-source-label"><span id="layout-source-title">待翻译文字</span><textarea id="layout-block-text" rows="12" placeholder="选中一个块可检查、修正待翻译文字。"></textarea></label><p class="layout-edit-small">只调整双语阅读中的分块，原 PDF 保持不变。重新分组或修改文字的块需重新翻译；旧译文和批注保留。</p></aside></div>
      <div class="layout-edit-footer"><span id="layout-edit-status" role="status"></span><button type="button" class="button layout-edit-close">取消</button><button type="button" class="button primary" id="layout-edit-save">保存调整</button></div>`;
    document.body.append(this.dialog);this.$=selector=>this.dialog.querySelector(selector);
    this.dialog.querySelectorAll('.layout-edit-close').forEach(b=>b.onclick=()=>{if(!this.saving)this.dialog.close();});
    this.dialog.addEventListener('cancel',e=>{if(this.saving)e.preventDefault();});
    this.dialog.querySelectorAll('[data-mode]').forEach(b=>b.onclick=()=>{this.mode=b.dataset.mode;this.render();});
    this.$('#layout-merge').onclick=()=>this.merge();
    this.$('#layout-select-all').onclick=()=>{this.mode='merge';this.selected=this.blocks.map(b=>b.id);this.render();};
    this.$('#layout-undo').onclick=()=>this.undo(false);this.$('#layout-redo').onclick=()=>this.undo(true);
    this.$('#layout-reset').onclick=()=>{this.record();this.blocks=clone(this.data.automatic);this.selected=[];this.reset=true;this.dirty=true;this.render();this.status('保存后恢复本页自动切分，可撤销。');};
    this.$('#layout-edit-save').onclick=()=>this.save();
    this.$('#layout-block-skip').onchange=e=>{const b=this.current();if(!b)return;this.record();b.skip=e.target.checked;this.changed();};
    this.$('#layout-block-text').onfocus=()=>{this.textRecorded=false;};
    this.$('#layout-block-text').oninput=e=>{const b=this.current();if(!b)return;if(!this.textRecorded){this.record();this.textRecorded=true;}b.text=e.target.value;this.reset=false;this.dirty=true;this.updateButtons();this.status('待保存：已修改本块的翻译文字。');};
    this.$('#layout-cut-apply').onclick=()=>{const b=this.current(),percent=Number(this.$('#layout-cut-percent').value);if(!b || !['horizontal','vertical'].includes(this.mode))return this.status('先选中一个块，并选择横向或纵向切分。',true);if(!Number.isFinite(percent)||percent<=0||percent>=100)return this.status('位置应在 1–99% 之间。',true);const axis=this.mode==='horizontal'?1:0;this.split(b,b.rect[axis]+(b.rect[axis+2]-b.rect[axis])*percent/100);};
    this.$('.layout-edit-board').onpointermove=e=>this.guide(e);
    this.$('.layout-edit-board').onpointerleave=()=>this.$('.layout-cut-line').hidden=true;
  }
  status(text,error=false){const el=this.$('#layout-edit-status');el.textContent=text;el.classList.toggle('error',error);const banner=this.$('#layout-edit-error');banner.hidden=!error;banner.textContent=error?text:'';}
  async open(number){
    if(this.busy())return this.notify('请先暂停翻译，再调整切分。');
    const id=this.documentId();if(!id)return;
    this.id=id;this.number=number;this.saving=true;this.saveFailed=false;this.dirty=false;this.selected=[];this.blocks=[];this.mode='select';this.past=[];this.future=[];this.reset=false;
    this.$('#layout-edit-page').textContent=number;this.$('.layout-edit-body').hidden=true;this.status('正在读取页面和文字位置…');this.dialog.showModal();this.updateButtons();
    try{
      this.data=await this.api(`/api/documents/${id}/layout/pages/${number}`);
      if(this.documentId()!==id){this.dialog.close();return;}
      this.blocks=clone(this.data.blocks);this.$('.layout-edit-board').style.aspectRatio=`${this.data.width}/${this.data.height}`;
      this.$('.layout-edit-board img').src=`/api/documents/${id}/pages/${number}/image`;
      this.$('.layout-edit-body').hidden=false;this.status('修改仅在点击「保存调整」后生效。');
    }catch(error){this.notify(error.message,true);this.dialog.close();}
    finally{this.saving=false;this.render();}
  }
  current(){return this.selected.length===1?this.blocks.find(b=>b.id===this.selected[0]):null;}
  snapshot(){return clone({blocks:this.blocks,selected:this.selected,reset:this.reset,dirty:this.dirty});}
  record(){this.past.push(this.snapshot());if(this.past.length>80)this.past.shift();this.future=[];}
  undo(redo){const from=redo?this.future:this.past,to=redo?this.past:this.future;if(!from.length)return;to.push(this.snapshot());Object.assign(this,from.pop());this.render();this.status(redo?'已重做。':'已撤销。');}
  changed(){this.reset=false;this.dirty=true;this.render();this.status('待保存：调整完成后点击「保存调整」。');}
  content(block){
    if(block.text!==undefined)return block.text;
    const grouped=new Map();
    for(const line of this.data.lines){if(!line.include||!centerIn(line,block.rect))continue;const list=grouped.get(line.paragraphId)||[];list.push(line);grouped.set(line.paragraphId,list);}
    return this.data.paragraphs.filter(p=>grouped.has(p.id)).map(p=>{
      const lines=grouped.get(p.id),all=this.data.lines.filter(l=>l.paragraphId===p.id&&l.include);
      return lines.length===all.length?p.translationSource||p.text:normalize(lines.map(l=>l.text).join('\n'));
    }).join('\n\n');
  }
  updateButtons(){
    this.$('#layout-edit-save').disabled=this.saving||!this.dirty;
    this.$('#layout-edit-save').textContent=this.saving?'处理中…':this.saveFailed?'重试保存':'保存调整';
    this.$('#layout-undo').disabled=this.saving||!this.past.length;this.$('#layout-redo').disabled=this.saving||!this.future.length;
    this.$('#layout-merge').disabled=this.saving||this.selected.length<2;
    this.$('#layout-reset').disabled=this.saving;
    this.$('#layout-select-all').disabled=this.saving;
  }
  render(){
    if(!this.data)return;this.updateButtons();
    this.dialog.querySelectorAll('[data-mode]').forEach(b=>{b.classList.toggle('active',b.dataset.mode===this.mode);b.setAttribute('aria-pressed',String(b.dataset.mode===this.mode));b.disabled=this.saving;});
    this.$('#layout-edit-help').textContent=this.mode==='select'?'点击块查看文字；Ctrl / Shift 点击可多选。':this.mode==='merge'?'连续点击要合并的相邻块，再点「合并所选」。':`在目标块内的${this.mode==='horizontal'?'行间':'栏间'}空白处点击切分，靠近文字时会尝试对齐到空白。`;
    const layer=this.$('.layout-edit-blocks');layer.replaceChildren();
    this.blocks.forEach((block,index)=>{
      const [x0,y0,x1,y1]=block.rect,b=document.createElement('button');b.type='button';b.className='layout-edit-block';b.dataset.blockId=block.id;b.setAttribute('aria-label',`原文块 ${index+1}`);b.setAttribute('aria-pressed',String(this.selected.includes(block.id)));
      b.classList.toggle('selected',this.selected.includes(block.id));b.classList.toggle('skipped',block.skip);b.style.cssText=`left:${x0/this.data.width*100}%;top:${y0/this.data.height*100}%;width:${(x1-x0)/this.data.width*100}%;height:${(y1-y0)/this.data.height*100}%`;
      const label=document.createElement('span');label.textContent=String(index+1)+(block.skip?' · 不翻译':'');b.append(label);
      b.onclick=e=>{if(this.saving)return;if(['horizontal','vertical'].includes(this.mode)&&e.detail){const point=this.point(e);this.split(block,point[this.mode==='horizontal'?1:0]);return;}const multi=this.mode==='merge'||e.ctrlKey||e.shiftKey;this.selected=multi?(this.selected.includes(block.id)?this.selected.filter(id=>id!==block.id):[...this.selected,block.id]):[block.id];this.render();};
      layer.append(b);
    });
    const block=this.current();this.$('#layout-block-title').textContent=block?`原文块 ${this.blocks.indexOf(block)+1}`:this.selected.length?`已选中 ${this.selected.length} 个块`:'选择原文块';
    this.$('#layout-block-text').value=block?this.content(block):'';this.$('#layout-block-text').disabled=!block||block.skip||this.saving;
    this.$('#layout-source-title').textContent=block?.skip?'此块文字（已排除翻译）':'待翻译文字';
    this.$('#layout-block-skip').checked=!!block?.skip;this.$('#layout-block-skip').disabled=!block||this.saving;this.$('.layout-cut-line').hidden=true;
  }
  point(event){const box=this.$('.layout-edit-board').getBoundingClientRect();return [(event.clientX-box.left)/box.width*this.data.width,(event.clientY-box.top)/box.height*this.data.height];}
  guide(event){const line=this.$('.layout-cut-line');if(!['horizontal','vertical'].includes(this.mode)||this.saving){line.hidden=true;return;}const [x,y]=this.point(event),block=this.blocks.find(b=>centerIn({rect:[x,y,x,y]},b.rect));if(!block)return;const r=block.rect;line.hidden=false;line.style.cssText=this.mode==='horizontal'?`left:${r[0]/this.data.width*100}%;top:${y/this.data.height*100}%;width:${(r[2]-r[0])/this.data.width*100}%;height:0`:`left:${x/this.data.width*100}%;top:${r[1]/this.data.height*100}%;height:${(r[3]-r[1])/this.data.height*100}%;width:0`;}
  split(block,position){
    const axis=this.mode==='horizontal'?1:0,r=block.rect;
    const lines=this.data.lines.filter(l=>l.protectBoundary!==false&&centerIn(l,r));
    const valid=p=>p>r[axis]+3&&p<r[axis+2]-3&&!lines.some(l=>l.rect[axis]-.4<p&&p<l.rect[axis+2]+.4);
    if(!valid(position)){
      const options=lines.flatMap(l=>[l.rect[axis]-.8,l.rect[axis+2]+.8]).filter(p=>Math.abs(p-position)<=8&&valid(p)).sort((a,b)=>Math.abs(a-position)-Math.abs(b-position));
      if(!options.length)return this.status('这里会切到文字或公式，请在行间、栏间空白处点击。',true);position=options[0];
    }
    this.record();const a={...clone(block),id:crypto.randomUUID(),regroup:true},b={...clone(block),id:crypto.randomUUID(),regroup:true};a.rect[axis+2]=position;b.rect[axis]=position;delete a.text;delete b.text;
    this.blocks.splice(this.blocks.indexOf(block),1,a,b);this.selected=[a.id];this.changed();
  }
  merge(){
    const selected=this.blocks.filter(b=>this.selected.includes(b.id));if(selected.length<2)return;
    const rect=[Math.min(...selected.map(b=>b.rect[0])),Math.min(...selected.map(b=>b.rect[1])),Math.max(...selected.map(b=>b.rect[2])),Math.max(...selected.map(b=>b.rect[3]))];
    const area=selected.reduce((sum,b)=>sum+(b.rect[2]-b.rect[0])*(b.rect[3]-b.rect[1]),0);
    if(Math.abs(area-(rect[2]-rect[0])*(rect[3]-rect[1]))>.1)return this.status('请选中紧邻且能组成矩形的块，不能跨过未选中的内容。',true);
    this.record();const block={id:crypto.randomUUID(),rect,regroup:true,skip:selected.every(b=>b.skip)};
    if(selected.some(b=>b.text!==undefined||b.skip))block.text=selected.filter(b=>!b.skip).map(b=>this.content(b)).join('\n\n');
    const index=this.blocks.indexOf(selected[0]);this.blocks=this.blocks.filter(b=>!this.selected.includes(b.id));this.blocks.splice(index,0,block);this.selected=[block.id];this.changed();
  }
  async save(){
    if(this.saving||!this.dirty)return;this.saving=true;this.render();this.status('正在保存切分和翻译段落…');
    try{const result=await this.api(`/api/documents/${this.id}/layout/pages/${this.number}`,{method:this.reset?'DELETE':'PUT',body:{revision:this.data.revision,blocks:this.blocks}});await this.onSave(result,this.number,this.id);this.dialog.close();this.notify(this.reset?'已恢复本页自动切分。':'切分已保存，调整过的文字可重新翻译。');}
    catch(error){this.saveFailed=true;this.status('未保存：'+error.message,true);}
    finally{this.saving=false;this.render();}
  }
}
