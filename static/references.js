import { t } from './i18n.js';

export class ReferenceLinks {
  constructor({getPdf,jump,notify}) {
    Object.assign(this,{getPdf,jump,notify});this.data={entries:{},citations:{}};
    this.menu=document.createElement('div');this.menu.className='reference-menu';this.menu.setAttribute('popover','auto');
    this.menu.setAttribute('aria-label',t('选择参考文献'));document.body.append(this.menu);
  }
  reset(data={entries:{},citations:{}}){this.data=data;this.menu.hidePopover();}
  choose(ids,anchor){
    if(!window.getSelection()?.isCollapsed)return;
    const entries=ids.map(id=>this.data.entries[id]).filter(Boolean);
    const open=entry=>{this.menu.hidePopover();this.jump({page:entry.page,x:entry.rect[0],y:entry.rect[1]});};
    if(entries.length===1)return open(entries[0]);
    if(!entries.length)return;
    this.menu.replaceChildren();
    for(const entry of entries){const button=document.createElement('button');button.dataset.userContent='';button.textContent=entry.text;button.dataset.referenceId=entry.id;button.onclick=()=>open(entry);this.menu.append(button);}
    const r=anchor.getBoundingClientRect();this.menu.showPopover();
    this.menu.style.left=`${Math.max(8,Math.min(r.left,innerWidth-this.menu.offsetWidth-8))}px`;
    this.menu.style.top=`${Math.max(8,Math.min(r.bottom+6,innerHeight-this.menu.offsetHeight-8))}px`;
  }
  async destination(value){
    const pdf=this.getPdf();
    try{
      const dest=typeof value==='string'?await pdf.getDestination(value):value;
      if(!dest)return this.notify('无法定位该引用。');
      const number=typeof dest[0]==='number'?dest[0]+1:await pdf.getPageIndex(dest[0])+1;
      const page=await pdf.getPage(number),v=page.getViewport({scale:1});
      if(pdf!==this.getPdf())return;
      let x=page.view[0],y=page.view[3];
      const type=dest[1]?.name;
      if(type==='XYZ'){x=dest[2]??x;y=dest[3]??y;}
      else if(['FitH','FitBH'].includes(type))y=dest[2]??y;
      else if(type==='FitR'){x=dest[2]??x;y=dest[5]??y;}
      const point=v.convertToViewportPoint(x,y);
      this.jump({page:number,x:point[0]/v.width,y:point[1]/v.height});
    }catch{this.notify('无法定位该引用。');}
  }
  mount(root,number,viewport,annotations=[]){
    root.querySelector(':scope > .link-overlays')?.remove();
    const layer=document.createElement('div');layer.className='link-overlays';root.append(layer);
    const native=[];
    const clip=root.closest('.source-crop')?.dataset.displayRect;
    const place=(rect,link)=>{
      if(clip){const c=JSON.parse(clip);rect=[Math.max(rect[0],c[0]),Math.max(rect[1],c[1]),Math.min(rect[2],c[2]),Math.min(rect[3],c[3])];}
      if(rect[2]<=rect[0]||rect[3]<=rect[1])return;
      link.style.cssText=`left:${rect[0]}px;top:${rect[1]}px;width:${rect[2]-rect[0]}px;height:${rect[3]-rect[1]}px`;layer.append(link);
    };
    for(const a of annotations){
      if(a.subtype!=='Link'||!a.rect?.every(Number.isFinite))continue;
      const p=viewport.convertToViewportPoint(a.rect[0],a.rect[1]),q=viewport.convertToViewportPoint(a.rect[2],a.rect[3]);
      const rect=[Math.min(p[0],q[0]),Math.min(p[1],q[1]),Math.max(p[0],q[0]),Math.max(p[1],q[1])];
      const link=document.createElement('a');link.title=a.url||t('跳转到引用');
      if(a.url&&/^https?:\/\//i.test(a.url)){link.href=a.url;link.target='_blank';link.rel='noopener noreferrer';}
      else if(a.dest){link.href='#';link.onclick=e=>{e.preventDefault();this.destination(a.dest);};}
      else continue;
      link.setAttribute('aria-label',link.title);native.push(rect);place(rect,link);
    }
    for(const hit of this.data.citations[String(number)]||[]){
      const rect=hit.rect.map((v,i)=>v*(i%2?viewport.height:viewport.width));
      if(native.some(n=>Math.min(n[2],rect[2])>Math.max(n[0],rect[0])&&Math.min(n[3],rect[3])>Math.max(n[1],rect[1])))continue;
      const link=document.createElement('a');link.href='#';link.dataset.referenceIds=hit.ids.join(',');
      link.title=t('跳转到引用')+` [${hit.ids.join(', ')}]`;link.setAttribute('aria-label',link.title);
      link.onclick=e=>{e.preventDefault();this.choose(hit.ids,link);};place(rect,link);
    }
  }
  decorate(root){
    const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT),nodes=[];
    while(walker.nextNode())if(!walker.currentNode.parentElement.closest('a,code,pre,.katex,.translation-annotation-layer'))nodes.push(walker.currentNode);
    for(const node of nodes){
      const regex=/\[(\d{1,4}(?:\s*[,，;；–—-]\s*\d{1,4})*)\]/g;let end=0,matched=false;const frag=document.createDocumentFragment();
      for(const match of node.data.matchAll(regex)){
        const ids=[];
        for(const part of match[1].split(/[,，;；]/)){const [first,last=first]=part.split(/[–—-]/).map(Number);if(last<first||last-first>100)continue;for(let n=first;n<=last;n++)if(this.data.entries[n])ids.push(String(n));}
        if(!ids.length)continue;
        frag.append(document.createTextNode(node.data.slice(end,match.index)));
        const link=document.createElement('a');link.href='#';link.className='reference-citation';link.textContent=match[0];link.dataset.referenceIds=[...new Set(ids)].join(',');
        link.title=t('跳转到引用');link.onclick=e=>{e.preventDefault();this.choose([...new Set(ids)],link);};frag.append(link);end=match.index+match[0].length;matched=true;
      }
      if(matched){frag.append(document.createTextNode(node.data.slice(end)));node.replaceWith(frag);}
    }
  }
}
