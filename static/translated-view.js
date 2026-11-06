import { paragraphRect } from './reading-position.js';
import { t } from './i18n.js';

const overlap=(a,b)=>Math.max(0,Math.min(a[2],b[2])-Math.max(a[0],b[0]))*Math.max(0,Math.min(a[3],b[3])-Math.max(a[1],b[1]));
function tiles(page){
  const walk=node=>node.tile?[node.tile]:(node.children||[]).flatMap(walk);
  return page.tree?walk(page.tree):page.rows.flatMap(row=>row.columns.flatMap(column=>column));
}

export function translatedItems(page,paragraphs,doc){
  const regions=tiles(page),groups=regions.map(()=>[]);
  for(const visual of page.visuals||[]){
    let index=0,area=-1;
    regions.forEach((tile,i)=>{const a=overlap(tile.rect,visual.rect);if(a>area){area=a;index=i;}});
    if(groups[index])groups[index].push(visual);
  }
  const byId=new Map(paragraphs.map(p=>[p.id,p])),used=new Set(),result=[];
  const append=p=>{if(p&&p.translatable!==false&&!used.has(p.id)){used.add(p.id);result.push({paragraph:p});}};
  regions.forEach((tile,index)=>{
    const own=tile.paragraphIds.map(id=>byId.get(id)).filter(p=>p&&p.translatable!==false);
    const insert=new Map();
    for(const visual of groups[index]){
      const r=visual.rect;
      // Preserve the document/manual paragraph order. Insert the artwork before
      // the next same-column paragraph; captions above a table stay above it.
      let before=own.findIndex(p=>{
        const b=paragraphRect(p,doc).map((v,i)=>v*(i%2?page.height:page.width));
        const horizontal=Math.min(r[2],b[2])-Math.max(r[0],b[0]);
        return b[1]>=r[1]-.5&&horizontal>Math.min(r[2]-r[0],b[2]-b[0])*.25;
      });
      if(before<0)before=own.length;
      if(!insert.has(before))insert.set(before,[]);insert.get(before).push(visual);
    }
    for(let i=0;i<=own.length;i++){
      for(const visual of (insert.get(i)||[]).sort((a,b)=>a.rect[1]-b.rect[1]||a.rect[0]-b.rect[0]))result.push({visual});
      if(i<own.length)append(own[i]);
    }
  });
  for(const p of paragraphs.filter(p=>p.page===page.page))append(p);
  return result;
}

export function renderTranslatedPages({container,layout,doc,paragraphs,paragraphCard,observe,preview}){
  const names={figure:'图片',table:'表格',formula:'公式'};
  for(const page of layout.pages){
    const section=document.createElement('section');section.className='translated-page';section.dataset.sourcePage=page.page;
    const heading=document.createElement('div');heading.className='translation-page-label';heading.textContent=`PAGE ${String(page.page).padStart(2,'0')}`;section.append(heading);
    for(const item of translatedItems(page,paragraphs,doc)){
      if(item.paragraph){section.append(paragraphCard(item.paragraph,false));continue;}
      const v=item.visual,[x0,y0,x1,y1]=v.rect;
      const figure=document.createElement('figure');figure.className='translation-visual';figure.dataset.visualId=v.id;figure.dataset.visualKind=v.kind;
      const label=`第 ${page.page} 页 · ${names[v.kind]||'图片'}`;
      const url=`/api/documents/${doc.id}/pages/${page.page}/visuals/${v.id}/image`;
      const caption=document.createElement('figcaption'),name=document.createElement('span'),zoom=document.createElement('button');
      name.textContent=label;zoom.type='button';zoom.className='text-button visual-zoom';zoom.textContent='放大查看';zoom.onclick=()=>preview(url,t(label));caption.append(name,zoom);
      const crop=document.createElement('div');crop.className='source-crop visual-crop';crop.style.aspectRatio=`${x1-x0} / ${y1-y0}`;
      // Respect the source size and viewport height, including small figures.
      // Bound the width (not just height) so the crop and its text layer keep
      // exactly the same aspect ratio and annotation coordinates.
      const ratio=(x1-x0)/(y1-y0),scale=v.kind==='formula'?1.5:2;
      crop.style.maxWidth=`min(${(x1-x0)*scale}px, ${640*ratio}px, ${70*ratio}dvh)`;
      crop.dataset.rect=JSON.stringify(v.rect);crop.dataset.displayRect=JSON.stringify(v.rect);crop.dataset.graphics='true';
      const image=document.createElement('img');image.dataset.src=url;image.decoding='async';image.draggable=false;image.alt=label;
      const retry=document.createElement('button');retry.type='button';retry.className='button visual-retry';retry.textContent='重试加载';retry.hidden=true;
      image.onerror=()=>{crop.classList.add('image-error');retry.hidden=false;};
      image.onload=()=>{crop.classList.remove('image-error');retry.hidden=true;};
      retry.onclick=()=>{retry.hidden=true;image.src=url;};
      crop.append(image,retry);figure.append(caption,crop);section.append(figure);
    }
    container.append(section);
    if(section.querySelector('.source-crop'))observe(section);
  }
}
