import policy from './reasoning-models.json' with {type:'json'};

const catalogs=new Map();
const key=config=>JSON.stringify([(config.baseUrl||'').trim().replace(/\/+$/,'').replace(/\/chat\/completions$/,''),(config.apiKey||'').trim()]);
export function rememberReasoning(config,values){catalogs.set(key(config),values||{});document.dispatchEvent(new Event('reasoning-catalog-changed'));}
export function availableEfforts(config){
  const model=(config.model||'').trim(),declared=catalogs.get(key(config))?.[model];
  if(Array.isArray(declared))return ['default',...policy.values.filter(value=>declared.includes(value))];
  let values=policy.models[model.replace(/-\d{4}-\d{2}-\d{2}$/,'')]||policy.fallback;
  let official=false;
  try{const url=new URL(config.baseUrl);official=url.protocol==='https:'&&url.hostname==='api.openai.com'&&(!url.port||url.port==='443');}catch{}
  if(!official)values=values.filter(value=>value!=='max');
  return ['default',...values];
}
export function normalizeEffort(config){return availableEfforts(config).includes(config.reasoningEffort)?config.reasoningEffort:'default';}
