// Hit-test painted annotations instead of placing buttons over the PDF text layer.
// This keeps native text selection, including dragging across existing highlights.
export class AnnotationActions {
  constructor({roots,getDocument,edit,onShow}) {
    Object.assign(this,{getDocument,edit,onShow});
    this.popup=document.createElement('div');this.popup.id='annotation-actions';
    this.popup.setAttribute('popover','manual');this.popup.setAttribute('role','dialog');
    this.popup.setAttribute('aria-label','批注快捷操作');document.body.append(this.popup);
    this.pointer=null;this.documentId=null;
    for(const root of roots) {
      root.addEventListener('pointerdown',event=>{
        this.pointer=event.button===0?{id:event.pointerId,x:event.clientX,y:event.clientY,moved:false}:null;
      });
      root.addEventListener('click',event=>this.clicked(event));
    }
    document.addEventListener('pointermove',event=>{
      if(this.pointer?.id===event.pointerId&&Math.hypot(event.clientX-this.pointer.x,event.clientY-this.pointer.y)>5)this.pointer.moved=true;
    },{passive:true});
    document.addEventListener('pointercancel',()=>{this.pointer=null;this.hide();});
    document.addEventListener('pointerdown',event=>{if(!this.popup.contains(event.target))this.hide();});
    document.addEventListener('scroll',event=>{
      if(!this.popup.matches(':popover-open')||this.popup.contains(event.target))return;
      // A scroll queued before the click can arrive after the popover opens.
      // Dismiss only when the marked content has actually scrolled since opening.
      if(this.scrollPositions?.some(({node,left,top})=>!node.isConnected||node.scrollLeft!==left||node.scrollTop!==top))this.hide();
    },true);
    document.addEventListener('keydown',event=>{
      if(event.key==='Escape'&&this.popup.matches(':popover-open')){event.preventDefault();this.hide();}
    });
    window.addEventListener('resize',()=>this.hide());
  }
  hide(){
    if(this.popup.matches(':popover-open'))this.popup.hidePopover();
    this.documentId=null;this.scrollPositions=null;
  }
  clicked(event){
    const moved=this.pointer?.moved;this.pointer=null;
    if(event.button!==0||event.detail>1||moved||!window.getSelection()?.isCollapsed)return this.hide();
    if(event.target.closest('button,a,input,select,textarea'))return;
    const region=event.target.closest('.translated-text,.source-crop,.page'),doc=this.getDocument();
    if(!region||!doc)return;
    const clip=region.getBoundingClientRect(),x=event.clientX,y=event.clientY;
    if(x<clip.left||x>clip.right||y<clip.top||y>clip.bottom)return;
    const ids=new Set();
    for(const mark of region.querySelectorAll('.annotation-mark[data-annotation-id]')){
      const box=mark.getBoundingClientRect();
      if(box.width&&box.height&&x>=box.left-2&&x<=box.right+2&&y>=box.top-2&&y<=box.bottom+2)ids.add(mark.dataset.annotationId);
    }
    const annotations=doc.state.annotations.filter(a=>ids.has(a.id));
    if(!annotations.length)return;
    this.show(annotations,doc.id,x,y,region);
  }
  show(annotations,docId,x,y,region){
    this.hide();this.documentId=docId;this.onShow();this.popup.replaceChildren();
    this.scrollPositions=[];
    for(let node=region;node;node=node.parentElement)this.scrollPositions.push({node,left:node.scrollLeft,top:node.scrollTop});
    const heading=document.createElement('div');heading.className='annotation-actions-heading';
    const label=document.createElement('strong');label.textContent=annotations.length>1?`此处有 ${annotations.length} 条批注`:'批注';
    const close=document.createElement('button');close.type='button';close.className='icon-button';close.textContent='×';close.setAttribute('aria-label','关闭批注快捷操作');close.onclick=()=>this.hide();
    heading.append(label,close);this.popup.append(heading);
    for(const annotation of annotations){
      const row=document.createElement('div');row.className='annotation-action-row';row.dataset.annotationId=annotation.id;
      const body=document.createElement('div');body.className='annotation-action-preview';
      const kind=document.createElement('span');kind.className='annotation-action-kind';kind.textContent={highlight:'高亮',underline:'下划线',note:'备注'}[annotation.kind];
      const preview=document.createElement('p');preview.dataset.userContent='';preview.textContent=annotation.note||annotation.text;preview.title=preview.textContent;
      const button=document.createElement('button');button.type='button';button.className='button annotation-quick-edit';button.textContent='编辑';button.setAttribute('aria-label','编辑备注');
      button.onclick=()=>{
        const current=this.getDocument(),item=current?.id===this.documentId?current.state.annotations.find(a=>a.id===annotation.id):null;
        this.hide();if(item)this.edit(item);
      };
      body.append(kind,preview);row.append(body,button);this.popup.append(row);
    }
    this.popup.showPopover();
    this.position(x,y);this.popup.querySelector('.annotation-quick-edit')?.focus({preventScroll:true});
    // Locale substitution may change the popup's height after this event.
    requestAnimationFrame(()=>{if(this.popup.matches(':popover-open'))this.position(x,y);});
  }
  position(x,y){
    const view=window.visualViewport,left=view?.offsetLeft||0,top=view?.offsetTop||0;
    const width=view?.width||window.innerWidth,height=view?.height||window.innerHeight;
    const box=this.popup.getBoundingClientRect(),gap=8;
    this.popup.style.left=`${Math.max(left+gap,Math.min(x,left+width-box.width-gap))}px`;
    const preferred=y+14+box.height<=top+height-gap?y+14:y-box.height-14;
    this.popup.style.top=`${Math.max(top+gap,Math.min(preferred,top+height-box.height-gap))}px`;
  }
}
