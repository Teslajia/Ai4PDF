import { TextLayer } from '/vendor/pdfjs-dist/build/pdf.mjs';

// Keep the original PDF appearance, but put its real, selectable text above it.
// Each text run belongs to exactly one crop; cloning a whole page per crop would
// put invisible duplicate text on the clipboard.
export async function sourceTextPage(pdf, number) {
  const page=await pdf.getPage(number), viewport=page.getViewport({scale:1});
  const content=await page.getTextContent();
  const families={'sans-serif':'Arial',serif:'Times New Roman',monospace:'Courier New'};
  for(const style of Object.values(content.styles))if(families[style.fontFamily])style.fontFamily=families[style.fontFamily];
  const holder=document.createElement('div');holder.className='source-page-plane source-measure';
  holder.style.width=`${viewport.width}px`;holder.style.height=`${viewport.height}px`;
  const layer=document.createElement('div');layer.className='textLayer';layer.lang=content.lang || '';
  holder.append(layer);document.body.append(holder);
  const textLayer=new TextLayer({textContentSource:content,container:layer,viewport});
  try {
    await textLayer.render();
    const box=holder.getBoundingClientRect();
    const runs=textLayer.textDivs.map(span=>{
      const r=span.getBoundingClientRect();
      return {node:span.cloneNode(true),rect:[r.left-box.left,r.top-box.top,r.right-box.left,r.bottom-box.top],
        eol:span.nextElementSibling?.tagName==='BR'};
    });
    return {viewport,layer:layer.cloneNode(false),runs};
  } finally { holder.remove(); }
}

export function mountSourceText(section, source, resizeObserver) {
  const crops=[...section.querySelectorAll('.source-crop')];
  const tiles=crops.map(crop=>({crop,rect:JSON.parse(crop.dataset.displayRect),layer:source.layer.cloneNode(false)}));
  for(const run of source.runs){
    let best=null,area=0;
    for(const tile of tiles){
      const a=tile.rect,b=run.rect,intersection=Math.max(0,Math.min(a[2],b[2])-Math.max(a[0],b[0]))*Math.max(0,Math.min(a[3],b[3])-Math.max(a[1],b[1]));
      if(intersection>area){area=intersection;best=tile;}
    }
    if(best){best.layer.append(run.node.cloneNode(true));if(run.eol)best.layer.append(document.createElement('br'));}
  }
  for(const {crop,layer} of tiles){
    const plane=document.createElement('div');plane.className='source-page-plane';
    plane.style.width=`${source.viewport.width}px`;plane.style.height=`${source.viewport.height}px`;
    plane.pdfViewport=source.viewport;
    const annotations=document.createElement('div');annotations.className='annotation-overlays';
    plane.append(layer,annotations);crop.append(plane);scaleSourceCrop(crop);resizeObserver.observe(crop);
  }
  section.dataset.selectable='true';
}

export function scaleSourceCrop(crop) {
  const plane=crop.querySelector('.source-page-plane');if(!plane)return;
  const [x0,y0,x1]=JSON.parse(crop.dataset.displayRect),scale=crop.getBoundingClientRect().width/(x1-x0);
  plane.style.transform=`translate(${-x0*scale}px,${-y0*scale}px) scale(${scale})`;
}

export function textNodes(element) {
  const walker=document.createTreeWalker(element,NodeFilter.SHOW_TEXT,{
    acceptNode:node=>node.parentElement.closest('.katex-mathml,.translation-annotation-layer') ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT
  });
  const result=[];while(walker.nextNode())result.push(walker.currentNode);return result;
}

export function selectedTextAnchor(element, range) {
  const nodes=textNodes(element),anchorText=nodes.map(n=>n.data).join('');
  let offset=0,start=null,end=null;
  for(const node of nodes){
    if(range.intersectsNode(node)){
      const a=node===range.startContainer?range.startOffset:0,b=node===range.endContainer?range.endOffset:node.length;
      if(b>a){if(start===null)start=offset+a;end=offset+b;}
    }
    offset+=node.length;
  }
  return start===null?null:{anchorText,start,end,text:anchorText.slice(start,end)};
}

function anchorRange(nodes,start,end) {
  const range=document.createRange();let offset=0,begun=false;
  for(const node of nodes){
    if(!begun && start<offset+node.length){range.setStart(node,start-offset);begun=true;}
    if(begun && end<=offset+node.length){range.setEnd(node,end-offset);return range;}
    offset+=node.length;
  }
  return null;
}

export function paintTextAnnotations(element, annotations, translationText) {
  element.querySelector('.translation-annotation-layer')?.remove();
  if(!element.isConnected || element.classList.contains('pending') || element.classList.contains('failed'))return;
  const nodes=textNodes(element),anchor=nodes.map(n=>n.data).join(''),box=element.getBoundingClientRect();
  if(!box.width || !box.height)return;
  const layer=document.createElement('div');layer.className='translation-annotation-layer';layer.setAttribute('aria-hidden','true');
  for(const annotation of annotations){
    if(annotation.translationText!==translationText || annotation.anchorText!==anchor)continue;
    const range=anchorRange(nodes,annotation.start,annotation.end);if(!range)continue;
    // Inspect each visible text node; a whole KaTeX range also includes hidden MathML.
    for(const node of nodes){
      if(!range.intersectsNode(node))continue;
      const part=document.createRange();part.selectNodeContents(node);
      if(node===range.startContainer)part.setStart(node,range.startOffset);
      if(node===range.endContainer)part.setEnd(node,range.endOffset);
      if(part.collapsed)continue;
      const parent=node.parentElement.closest('.katex-display'),clip=parent?.getBoundingClientRect();
      for(const r of part.getClientRects()){
        const left=Math.max(r.left,box.left,clip?.left??-Infinity),top=Math.max(r.top,box.top);
        const right=Math.min(r.right,box.right,clip?.right??Infinity),bottom=Math.min(r.bottom,box.bottom);
        if(right-left<.5 || bottom-top<.5)continue;
        const mark=document.createElement('span');mark.className=`annotation-mark ${annotation.kind}`;mark.dataset.annotationId=annotation.id;
        mark.style.cssText=`left:${left-box.left-element.clientLeft}px;top:${top-box.top-element.clientTop}px;width:${right-left}px;height:${bottom-top}px;background:${annotation.color};border-color:${annotation.color}`;
        layer.append(mark);
      }
    }
  }
  element.append(layer);
}

export function sourceSelection(range, views) {
  const groups=new Map();
  for(const {number,element,viewport,clipElement=element} of views){
    if(!range.intersectsNode(element))continue;
    const box=element.getBoundingClientRect(),clip=clipElement.getBoundingClientRect();
    if(!box.width || !box.height)continue;
    const group=groups.get(number)||{page:number,rects:[],quads:[],snippets:[]};
    for(const span of element.querySelectorAll('.textLayer span')){
      if(span.firstChild?.nodeType!==Node.TEXT_NODE || !range.intersectsNode(span))continue;
      const sub=document.createRange();sub.selectNodeContents(span);
      if(span.contains(range.startContainer))sub.setStart(range.startContainer,range.startOffset);
      if(span.contains(range.endContainer))sub.setEnd(range.endContainer,range.endOffset);
      if(sub.collapsed)continue;
      let visible=false;
      for(const r of sub.getClientRects()){
        const x=Math.max(0,r.left-box.left,clip.left-box.left),y=Math.max(0,r.top-box.top,clip.top-box.top);
        const right=Math.min(box.width,r.right-box.left,clip.right-box.left),bottom=Math.min(box.height,r.bottom-box.top,clip.bottom-box.top);
        if(right-x<.5 || bottom-y<.5)continue;
        group.rects.push([x/box.width,y/box.height,(right-x)/box.width,(bottom-y)/box.height]);
        const quad=[];
        for(const [a,b] of [[x,y],[right,y],[x,bottom],[right,bottom]])quad.push(...viewport.convertToPdfPoint(a/box.width*viewport.width,b/box.height*viewport.height));
        group.quads.push(quad);visible=true;
      }
      if(visible)group.snippets.push(sub.toString());
    }
    if(group.rects.length)groups.set(number,group);
  }
  return [...groups.values()].map(({snippets,...group})=>({...group,text:snippets.join(' ')}));
}
