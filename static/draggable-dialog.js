// Move a dialog without transforms: its text and controls stay crisp at any zoom.
// Keep modal focus/selection behavior intact while allowing the paper to show through.
export function draggableDialog(dialog, handle) {
  let position=null, drag=null;
  const viewport=()=>{
    const view=window.visualViewport;
    return {left:view?.offsetLeft||0,top:view?.offsetTop||0,width:view?.width||window.innerWidth,height:view?.height||window.innerHeight};
  };
  function place(x,y){
    const view=viewport(),rect=dialog.getBoundingClientRect(),gap=8;
    const left=Math.max(view.left+gap,Math.min(x,view.left+view.width-rect.width-gap));
    const top=Math.max(view.top+gap,Math.min(y,view.top+view.height-rect.height-gap));
    position={left,top};dialog.style.left=`${left}px`;dialog.style.top=`${top}px`;
  }
  function fit(){
    if(!dialog.open)return;
    const view=viewport(),rect=dialog.getBoundingClientRect();
    place(position?.left??view.left+(view.width-rect.width)/2,position?.top??view.top+(view.height-rect.height)/2);
  }
  function end(){
    if(drag&&handle.hasPointerCapture(drag.id))handle.releasePointerCapture(drag.id);
    drag=null;handle.classList.remove('is-dragging');
  }
  handle.addEventListener('pointerdown',event=>{
    if(event.button!==0||!event.isPrimary||event.target.closest('button,a,input,textarea,select'))return;
    const rect=dialog.getBoundingClientRect();
    drag={id:event.pointerId,x:event.clientX,y:event.clientY,left:rect.left,top:rect.top};
    handle.setPointerCapture(event.pointerId);handle.classList.add('is-dragging');
    // Preserve textarea focus and the original PDF text selection while dragging.
    event.preventDefault();
  });
  handle.addEventListener('pointermove',event=>{
    if(drag?.id===event.pointerId)place(drag.left+event.clientX-drag.x,drag.top+event.clientY-drag.y);
  });
  for(const type of ['pointerup','pointercancel','lostpointercapture'])handle.addEventListener(type,end);
  handle.addEventListener('keydown',event=>{
    if(event.target!==handle||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key))return;
    event.preventDefault();const rect=dialog.getBoundingClientRect(),step=event.shiftKey?40:10;
    place(rect.left+(event.key==='ArrowRight'?step:event.key==='ArrowLeft'?-step:0),rect.top+(event.key==='ArrowDown'?step:event.key==='ArrowUp'?-step:0));
  });
  dialog.addEventListener('close',end);
  new ResizeObserver(fit).observe(dialog);
  window.addEventListener('resize',fit);
  window.visualViewport?.addEventListener('resize',fit);
  window.visualViewport?.addEventListener('scroll',fit);
  return {fit};
}
