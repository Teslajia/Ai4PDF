const MAX_IMAGES=4, MAX_BYTES=10*1024*1024;
const imageFile=file=>/^image\/(png|jpeg|webp)$/.test(file.type) || (!file.type && /\.(png|jpe?g|webp)$/i.test(file.name));
export function attachmentURL(docId,image){
  return /^[a-f0-9]{24}$/.test(docId) && /^[a-f0-9]{32}$/.test(image.id)
    ? `/api/documents/${docId}/attachments/${image.id}` : '';
}
export function previewImage(url,name){
  const dialog=document.querySelector('#image-dialog');
  dialog.querySelector('img').src=url;
  dialog.querySelector('img').alt=name;
  dialog.querySelector('.image-preview-name').textContent=name;
  dialog.showModal();
}
export function appendMessageImages(container,attachments,docId){
  if(!attachments?.length)return;
  const gallery=document.createElement('div');gallery.className='message-images';
  for(const attachment of attachments){
    const url=attachmentURL(docId,attachment);if(!url)continue;
    const button=document.createElement('button');button.type='button';button.title=attachment.name;
    button.setAttribute('aria-label','查看图片：'+attachment.name);
    const image=document.createElement('img');image.src=url;image.alt=attachment.name;image.loading='lazy';
    button.append(image);button.onclick=()=>previewImage(url,attachment.name);gallery.append(button);
  }
  container.append(gallery);
}

export class ChatImages {
  constructor({api,notify,busy,documentId}){
    Object.assign(this,{api,notify,busy,documentId});this.items=[];this.generation=0;
    this.container=document.querySelector('#chat-attachments');
    this.input=document.querySelector('#chat-image-input');
    this.button=document.querySelector('#attach-image');
    this.button.onclick=()=>{if(!this.documentId())return this.notify('请先打开一份 PDF。');this.input.click();};
    this.input.onchange=()=>{this.add(this.input.files);this.input.value='';};
    document.querySelector('#question').addEventListener('paste',event=>{
      const files=[...(event.clipboardData?.files||[])].filter(imageFile);
      if(files.length){event.preventDefault();this.add(files);}
    });
    const assistant=document.querySelector('.assistant');
    const imageDrag=event=>[...(event.dataTransfer?.items||[])].some(item=>item.kind==='file' && item.type.startsWith('image/'));
    for(const type of ['dragenter','dragover'])assistant.addEventListener(type,event=>{
      if(imageDrag(event)){event.preventDefault();event.stopPropagation();assistant.classList.add('image-dragover');document.querySelector('#drop-overlay').hidden=true;}
    });
    assistant.addEventListener('dragleave',event=>{if(!assistant.contains(event.relatedTarget))assistant.classList.remove('image-dragover');});
    assistant.addEventListener('drop',event=>{
      assistant.classList.remove('image-dragover');
      const files=[...(event.dataTransfer?.files||[])];
      if(files.some(imageFile)){event.preventDefault();event.stopPropagation();document.querySelector('#drop-overlay').hidden=true;this.add(files);}
    });
    const dialog=document.querySelector('#image-dialog');
    dialog.addEventListener('close',()=>dialog.querySelector('img').removeAttribute('src'));
    dialog.addEventListener('click',event=>{if(event.target===dialog)dialog.close();});
  }
  get preparing(){return this.items.some(item=>item.preparing);}
  clear(){this.generation++;for(const item of this.items)if(item.local)URL.revokeObjectURL(item.url);this.items=[];this.render();}
  restore(attachments,docId){
    this.clear();this.items=attachments.map(attachment=>({attachment,url:attachmentURL(docId,attachment),name:attachment.name}));this.render();
  }
  render(){
    this.container.replaceChildren();this.container.hidden=!this.items.length;
    this.button.disabled=this.busy() || this.items.length>=MAX_IMAGES;
    for(const item of this.items){
      const tile=document.createElement('div');tile.className='chat-image';
      const preview=document.createElement('button');preview.type='button';preview.className='chat-image-preview';preview.title=item.name;preview.setAttribute('aria-label','预览图片：'+item.name);
      const img=document.createElement('img');img.src=item.url;img.alt=item.name;preview.append(img);preview.onclick=()=>previewImage(item.url,item.name);
      const remove=document.createElement('button');remove.type='button';remove.className='remove-image';remove.textContent='×';remove.disabled=this.busy();remove.setAttribute('aria-label','移除图片：'+item.name);
      remove.onclick=()=>{if(this.busy())return;if(item.local)URL.revokeObjectURL(item.url);this.items=this.items.filter(i=>i!==item);this.render();};
      tile.append(preview,remove);
      if(item.preparing){const status=document.createElement('span');status.className='image-preparing';status.textContent='读取中';tile.append(status);}
      this.container.append(tile);
    }
    const hint=document.querySelector('#chat-image-hint');hint.hidden=!this.items.length;
    hint.textContent=`${this.items.length} / ${MAX_IMAGES} 张 · 发送需使用支持图片的模型`;
  }
  async add(files){
    if(this.busy())return this.notify('请等待当前回答结束后再添加图片。');
    if(!this.documentId())return this.notify('请先打开一份 PDF。');
    const generation=this.generation;
    for(const file of Array.from(files)){
      if(generation!==this.generation)return;
      if(!imageFile(file)){this.notify('支持 PNG、JPEG 和 WebP 图片。',true);continue;}
      if(file.size>MAX_BYTES){this.notify('每张图片不能超过 10 MB。',true);continue;}
      if(this.items.length>=MAX_IMAGES){this.notify('每条消息最多添加 4 张图片。',true);break;}
      const item={name:file.name,url:URL.createObjectURL(file),local:true,preparing:true,file};
      this.items.push(item);this.render();
      try{
        const img=new Image();img.src=item.url;await img.decode();
        if(img.naturalWidth*img.naturalHeight>25_000_000)throw new Error('图片像素过大，请缩小到 2500 万像素以内。');
        if(file.type==='image/webp' || /\.webp$/i.test(file.name)){
          const canvas=document.createElement('canvas');canvas.width=img.naturalWidth;canvas.height=img.naturalHeight;
          canvas.getContext('2d').drawImage(img,0,0);
          const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));
          if(!blob || blob.size>MAX_BYTES)throw new Error('这张 WebP 转换后超过 10 MB，请缩小图片后再添加。');
          item.file=new File([blob],file.name.replace(/\.webp$/i,'')+'.png',{type:'image/png'});
        }
        item.preparing=false;
      }catch(error){
        if(this.items.includes(item))this.notify(error.message.includes('MB') || error.message.includes('像素')?error.message:'无法读取图片，请使用有效的 PNG、JPEG 或 WebP 图片。',true);
        this.items=this.items.filter(i=>i!==item);URL.revokeObjectURL(item.url);
      }
      if(generation!==this.generation)return;
      this.render();
    }
  }
  async upload(docId){
    if(this.preparing)throw new Error('图片正在读取，请稍后发送。');
    for(const item of this.items){
      if(item.attachment)continue;
      const form=new FormData();form.append('file',item.file);
      item.attachment=await this.api(`/api/documents/${docId}/attachments`,{method:'POST',body:form});
    }
    return this.items.map(item=>item.attachment);
  }
}
