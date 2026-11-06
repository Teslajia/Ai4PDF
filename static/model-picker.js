// Provider catalogs stay in memory, scoped to the endpoint and credentials.
// Only explicitly requested model-list lookups contact the configured provider.
import { rememberReasoning } from './reasoning.js';
const catalogs = new Map();
const connectionKey = ({baseUrl='',apiKey=''}) => JSON.stringify([baseUrl.trim().replace(/\/+$/,''),apiKey.trim()]);

export class ModelPicker {
  constructor({root,getConnection,getRecent,onResize=()=>{}}) {
    this.root=root;this.getConnection=getConnection;this.getRecent=getRecent;this.onResize=onResize;
    this.input=root.querySelector('input');this.prefix=this.input.id;this.controller=null;this.requestId=0;
    const label=root.querySelector('label'),heading=document.createElement('div');heading.className='model-field-heading';
    this.fetchButton=document.createElement('button');this.fetchButton.type='button';this.fetchButton.className='model-fetch text-button';this.fetchButton.id=this.prefix+'-fetch';this.fetchButton.textContent='获取模型';
    heading.append(label,this.fetchButton);
    const row=document.createElement('div');row.className='model-input-row';
    this.toggle=document.createElement('button');this.toggle.type='button';this.toggle.className='model-list-toggle';this.toggle.id=this.prefix+'-toggle';
    this.toggle.textContent='▾';this.toggle.setAttribute('aria-label','选择模型');this.toggle.setAttribute('aria-expanded','false');this.toggle.setAttribute('aria-controls',this.prefix+'-list');
    row.append(this.input,this.toggle);
    this.panel=document.createElement('div');this.panel.className='model-picker-list';this.panel.id=this.prefix+'-list';this.panel.hidden=true;
    this.search=document.createElement('input');this.search.type='search';this.search.autocomplete='off';this.search.placeholder='搜索模型…';this.search.setAttribute('aria-label','搜索模型');
    this.results=document.createElement('div');this.results.className='model-picker-results';
    this.panel.append(this.search,this.results);
    this.status=document.createElement('p');this.status.className='model-picker-status';this.status.setAttribute('role','status');this.status.id=this.prefix+'-hint';this.input.setAttribute('aria-describedby',this.status.id);
    root.replaceChildren(heading,row,this.panel,this.status);
    this.toggle.onclick=()=>this.panel.hidden?this.open():this.close();
    this.fetchButton.onclick=()=>this.fetchModels();
    this.search.oninput=()=>this.render();
    this.input.onkeydown=e=>{if(e.key==='ArrowDown'){e.preventDefault();this.open();}};
    this.panel.onkeydown=e=>{
      if(e.key==='Escape'){e.preventDefault();e.stopPropagation();this.close();this.toggle.focus();}
      else if(e.key==='Enter'&&e.target===this.search){e.preventDefault();this.results.querySelector('button')?.click();}
      else if(['ArrowDown','ArrowUp'].includes(e.key)){
        e.preventDefault();const items=[...this.results.querySelectorAll('button')],i=items.indexOf(document.activeElement);
        items[Math.max(0,Math.min(items.length-1,i+(e.key==='ArrowDown'?1:-1)))]?.focus();
      }
    };
    this.reset();
  }
  catalog(){return catalogs.get(connectionKey(this.getConnection()));}
  info(message,error=false){this.status.textContent=message;this.status.classList.toggle('error',error);this.onResize();}
  reset(){
    this.controller?.abort();this.controller=null;this.requestId++;
    this.fetchButton.disabled=false;this.fetchButton.textContent='获取模型';this.close();
    const catalog=this.catalog();
    this.info(catalog?`已获取 ${catalog.length} 个模型。请选择支持对话的模型。`:'点击「获取模型」读取当前 API 的列表，也可手动输入。');
  }
  open(){this.search.value='';this.panel.hidden=false;this.toggle.setAttribute('aria-expanded','true');this.render();this.search.focus();this.onResize();}
  close(){this.panel.hidden=true;this.toggle.setAttribute('aria-expanded','false');this.onResize();}
  render(){
    const query=this.search.value.trim().toLowerCase(),remote=this.catalog()||[];
    const recent=[...new Set([this.input.value.trim(),...this.getRecent()].filter(Boolean))].filter(id=>!remote.includes(id));
    this.results.replaceChildren();
    for(const [label,models] of [['API 返回的模型',remote],['当前 / 最近使用',recent]]){
      const filtered=models.filter(id=>id.toLowerCase().includes(query));if(!filtered.length)continue;
      const heading=document.createElement('div');heading.className='model-picker-group';heading.textContent=label;this.results.append(heading);
      for(const id of filtered){
        const option=document.createElement('button');option.type='button';option.className='model-choice';option.textContent=id;option.title=id;
        option.classList.toggle('selected',id===this.input.value.trim());
        option.onclick=()=>{this.input.value=id;this.input.dispatchEvent(new Event('input',{bubbles:true}));this.close();this.input.focus();};
        this.results.append(option);
      }
    }
    if(!this.results.childElementCount){const empty=document.createElement('p');empty.className='model-picker-empty';empty.textContent=query?'没有匹配的模型，仍可在上方手动输入。':'暂无模型，请先点击「获取模型」。';this.results.append(empty);}
  }
  async fetchModels(){
    const config=this.getConnection(),key=connectionKey(config);
    if(!config.baseUrl.trim()){this.info('请先在连接设置中填写 API 地址。',true);return;}
    this.controller?.abort();const controller=new AbortController(),id=++this.requestId;this.controller=controller;
    this.fetchButton.disabled=true;this.fetchButton.textContent='获取中…';this.info('正在获取当前 API 的模型列表…');
    try{
      const response=await fetch('/api/models',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({config:{baseUrl:config.baseUrl,apiKey:config.apiKey}}),signal:controller.signal});
      const result=await response.json();
      if(id!==this.requestId||key!==connectionKey(this.getConnection()))return;
      if(!response.ok)throw new Error(result.error||'获取模型列表失败。');
      catalogs.set(key,result.models);
      rememberReasoning(config,result.reasoningEfforts);
      this.info(result.models.length?`已获取 ${result.models.length} 个模型。请选择支持对话的模型。`:'API 返回了空列表，仍可手动填写模型 ID。');
      this.open();
    }catch(error){
      if(error.name!=='AbortError'&&id===this.requestId&&key===connectionKey(this.getConnection()))this.info(error.message||'获取模型列表失败，请重试。',true);
    }finally{
      if(id===this.requestId){this.controller=null;this.fetchButton.disabled=false;this.fetchButton.textContent='获取模型';this.onResize();}
    }
  }
}
