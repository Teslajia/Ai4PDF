// Anchors use page coordinates and paragraph IDs, so rebuilding the DOM or
// changing zoom does not turn a saved position into a stale pixel offset.
const clamp=value=>Math.max(0,Math.min(1,value));
const $=selector=>document.querySelector(selector);

export function paragraphRect(paragraph,document){
  const size=document.pages[paragraph.page-1],b=paragraph.bbox;
  if(!size||!b)return [0,0,1,1];
  const {width:w,height:h,rotation:r}=size;
  let rect=b;
  if(r===90)rect=[w-b[3],b[0],w-b[1],b[2]];
  else if(r===180)rect=[w-b[2],h-b[3],w-b[0],h-b[1]];
  else if(r===270)rect=[b[1],h-b[2],b[3],h-b[0]];
  return rect.map((v,i)=>v/(i%2?h:w));
}

export class ReadingPosition {
  constructor({getDocument,getMode,getParagraphs}){Object.assign(this,{getDocument,getMode,getParagraphs});}
  nearest(page,x,y){
    let best=null,distance=Infinity;
    for(const p of this.getParagraphs()){
      if(p.page!==page||p.translatable===false)continue;
      const r=paragraphRect(p,this.getDocument());
      const d=Math.max(r[1]-y,0,y-r[3])*3+Math.max(r[0]-x,0,x-r[2]);
      if(d<distance){best=p;distance=d;}
    }
    return best;
  }
  capture(){
    const doc=this.getDocument(),mode=this.getMode();if(!doc)return null;
    const root=$(mode==='pdf'?'#pdf-scroll':'#translation-view');if(root.hidden)return null;
    const edge=root.getBoundingClientRect().top+80;
    const anchor={mode,display:$('#translation-display').value,page:1,x:.1,y:0,fraction:0,atTop:root.scrollTop<2,left:root.scrollLeft};
    if(mode==='pdf'){
      const pages=[...root.querySelectorAll('.page')];
      const el=pages.find(el=>el.getBoundingClientRect().bottom>edge)||pages.at(-1);if(!el)return null;
      const r=el.getBoundingClientRect();anchor.page=Number(el.dataset.pageNumber);anchor.y=clamp((edge-r.top)/r.height);
      // Use the visible horizontal position when zoomed beyond the reader width.
      anchor.x=clamp((root.getBoundingClientRect().left+root.clientWidth*.25-r.left)/r.width);
    }else{
      const elements=[...root.querySelectorAll('.paragraph,.source-crop')];
      let el=null,best=Infinity;
      for(const item of elements){
        const r=item.getBoundingClientRect();if(!r.height)continue;
        const d=(r.bottom<edge?edge-r.bottom:Math.max(0,r.top-edge));
        if(d<best){el=item;best=d;}
      }
      if(!el)return anchor;
      const r=el.getBoundingClientRect();anchor.fraction=clamp((edge-r.top)/r.height);
      if(el.classList.contains('paragraph')){
        const p=this.getParagraphs().find(p=>p.id===el.dataset.paragraphId);if(!p)return anchor;
        anchor.page=p.page;anchor.paragraphId=p.id;anchor.kind='paragraph';
        const b=paragraphRect(p,doc);anchor.x=(b[0]+b[2])/2;anchor.y=b[1]+(b[3]-b[1])*anchor.fraction;
      }else{
        anchor.kind='crop';anchor.page=Number(el.closest('[data-source-page]').dataset.sourcePage);
        const b=JSON.parse(el.dataset.displayRect),size=doc.pages[anchor.page-1];
        anchor.x=(b[0]+b[2])/2/size.width;anchor.y=(b[1]+(b[3]-b[1])*anchor.fraction)/size.height;
      }
    }
    if(!anchor.paragraphId){
      const p=this.nearest(anchor.page,anchor.x,anchor.y);
      if(p){anchor.paragraphId=p.id;const r=paragraphRect(p,doc);anchor.paragraphFraction=clamp((anchor.y-r[1])/Math.max(.001,r[3]-r[1]));}
    }
    return anchor;
  }
  restore(anchor,{exact=false}={}){
    const doc=this.getDocument(),mode=this.getMode();if(!doc||!anchor)return;
    const root=$(mode==='pdf'?'#pdf-scroll':'#translation-view');
    if(anchor.atTop&&(exact||anchor.page===1)){root.scrollTop=0;root.scrollLeft=anchor.left||0;return;}
    let el,fraction=anchor.fraction||0;
    if(mode==='pdf'){
      el=root.querySelector(`.page[data-page-number="${anchor.page}"]`);fraction=anchor.y||0;
    }else{
      if(anchor.kind==='crop'&&(mode==='translated'||$('#translation-display').value==='layout')){
        const size=doc.pages[anchor.page-1];
        el=[...root.querySelectorAll(`[data-source-page="${anchor.page}"] .source-crop`)].find(c=>{
          const b=JSON.parse(c.dataset.displayRect),x=anchor.x*size.width,y=anchor.y*size.height;
          if(x<b[0]-.5||x>b[2]+.5||y<b[1]-.5||y>b[3]+.5)return false;
          fraction=clamp((y-b[1])/(b[3]-b[1]));return true;
        });
      }
      if(!el&&anchor.paragraphId){el=document.getElementById(`para-${anchor.paragraphId}`);fraction=anchor.kind==='paragraph'?anchor.fraction:anchor.paragraphFraction||0;}
      if(!el){el=root.querySelector(`[data-source-page="${anchor.page}"]`);fraction=0;}
    }
    if(!el)return;
    const r=el.getBoundingClientRect();root.scrollTop+=r.top-root.getBoundingClientRect().top+r.height*clamp(fraction)-80;
    if(mode==='pdf'){
      root.scrollLeft=exact?(anchor.left||0):Math.max(0,el.offsetLeft+(anchor.x||0)*el.clientWidth-root.clientWidth*.25);
    }
  }
  save(anchor=this.capture()){
    const doc=this.getDocument();if(!doc||!anchor)return;
    try{
      const saved=JSON.parse(localStorage.getItem('paperdesk.readingPositions')||'{}');
      const previous=saved[doc.id];
      const pdf=anchor.mode==='pdf'?anchor:previous?.pdf||(previous?.mode==='pdf'?previous:null);
      delete saved[doc.id];saved[doc.id]={...anchor,pdf};
      const entries=Object.entries(saved).slice(-50);localStorage.setItem('paperdesk.readingPositions',JSON.stringify(Object.fromEntries(entries)));
    }catch{/* Reading must remain usable if browser storage is unavailable. */}
  }
  load(){
    try{
      const saved=JSON.parse(localStorage.getItem('paperdesk.readingPositions')||'{}')[this.getDocument()?.id];
      // Reopening a document starts in PDF mode at its own last position.
      const value=saved?.pdf||saved;
      if(value&&Number.isInteger(value.page)&&value.page>0&&value.page<=this.getDocument().pageCount&&Number.isFinite(value.y)&&Number.isFinite(value.x))return value;
    }catch{}
    return null;
  }
}
