const $=selector=>document.querySelector(selector);
export class UpdatesUI {
  constructor({api,busy,flush}){
    Object.assign(this,{api,busy,flush});
    this.pending=false;this.timer=null;
    $('#update-check').onclick=()=>this.action('/check');
    $('#update-download').onclick=()=>this.action('/download');
    $('#update-install').onclick=()=>this.install();
    $('#settings-dialog').addEventListener('close',()=>clearTimeout(this.timer));
    $('#update-restart-dialog').addEventListener('cancel',event=>event.preventDefault());
  }
  async load(){
    clearTimeout(this.timer);
    try{this.render(await this.api('/api/updates'));}catch(e){this.error(e.message);}
  }
  error(message){$('#update-status').textContent=message;$('#update-status').classList.add('error');}
  async action(path){
    if(this.pending)return;
    this.pending=true;$('#update-check').disabled=true;$('#update-download').disabled=true;
    if(path==='/check')$('#update-status').textContent='正在检查 GitHub Release…';
    try{this.render(await this.api('/api/updates'+path,{method:'POST',body:{}}));}
    catch(e){this.error(e.message);}
    finally{this.pending=false;$('#update-check').disabled=['downloading','installing','checking'].includes(this.data?.state);$('#update-download').disabled=false;}
  }
  render(data){
    this.data=data;
    const release=data.release,state=data.state;
    $('#update-current').textContent=`Ai4PDF ${data.currentVersion}`;
    $('#update-mode').hidden=data.canInstall;
    $('#update-check').disabled=['checking','downloading','installing'].includes(state);
    $('#update-download').hidden=!(data.canInstall&&release?.isNew&&release.canDownload&&['available','error'].includes(state));
    $('#update-install').hidden=!(state==='ready'&&data.canInstall);
    $('#update-release').href=release?.url||'https://github.com/Teslajia/Ai4PDF/releases/latest';
    const message={idle:'点击检查 GitHub 上的最新正式版本。',checking:'正在检查 GitHub Release…',
      current:'当前已是最新版本。',available:release?.canDownload?'发现新版本：{version}':'新版本暂未提供可校验的 Windows 安装包，请查看发布页面。',
      downloading:'正在下载安装包：{progress}%',ready:'下载完成，校验通过。可以安装更新。',installing:'正在安装更新，请等待软件重新启动。',error:data.error}[state]||'';
    const percent=Math.min(100,Math.floor(data.downloaded/(release?.size||1)*100));
    $('#update-status').textContent=message.replace('{version}',release?.version||'').replace('{progress}',String(percent));
    $('#update-status').classList.toggle('error',state==='error');
    const progress=$('#update-progress');progress.hidden=state!=='downloading';progress.value=percent;
    $('#update-notes').hidden=!release?.isNew||!release.notes;
    $('#update-notes-text').textContent=release?.notes||'';
    clearTimeout(this.timer);
    if(['downloading','checking'].includes(state)&&$('#settings-dialog').open)this.timer=setTimeout(()=>this.load(),800);
  }
  async install(){
    if(this.pending)return;
    if(this.busy())return this.error('请等待文档保存、翻译、问答或文档库迁移完成后再安装。');
    this.pending=true;$('#update-install').disabled=true;
    try{
      await this.flush();
      if(this.busy())throw new Error('请等待文档保存、翻译、问答或文档库迁移完成后再安装。');
      const expected=this.data.release.version;
      this.render(await this.api('/api/updates/install',{method:'POST',body:{}}));
      // Prevent unsaved UI changes while the local service is shutting down.
      $('#settings-dialog').close();
      const dialog=$('#update-restart-dialog');dialog.showModal();
      let attempts=0,offline=false;
      const poll=async()=>{
        attempts++;
        try{
          const health=await this.api('/api/health');
          if(health.version===expected){location.reload();return;}
          if(offline){$('#update-restart-status').textContent='更新未完成，原版本已重新启动。请重试或查看发布页面。';$('#update-return').hidden=false;return;}
        }catch{offline=true;}
        if(attempts<150)this.timer=setTimeout(poll,2000);
        else{$('#update-restart-status').textContent='尚未连接到更新后的程序，请完成安装，或从桌面重新打开 Ai4PDF。';$('#update-return').hidden=false;}
      };
      $('#update-return').onclick=()=>location.reload();
      this.timer=setTimeout(poll,2000);
    }catch(e){this.error(e.message);}
    finally{this.pending=false;$('#update-install').disabled=false;}
  }
}
