import { messages as baseMessages } from './locales.js';
import { libraryMessages } from './library-locales.js';

const messages=[...baseMessages,...libraryMessages];

export const locales=['zh-CN','zh-TW','ko','ja','en'];
let current='zh-CN';
try{const saved=localStorage.getItem('paperdesk.locale');if(locales.includes(saved))current=saved;}catch{}
export const getLocale=()=>current;
const exact=new Map(messages.map(row=>[row[0],row]));
const patterns=messages.filter(row=>/\{\w+\}/.test(row[0])).sort((a,b)=>b[0].replace(/\{\w+\}/g,'').length-a[0].replace(/\{\w+\}/g,'').length).map(row=>{
  const keys=[];
  const pattern=row[0].split(/(\{\w+\})/).map(part=>{
    if(/^\{\w+\}$/.test(part)){keys.push(part.slice(1,-1));return '([\\s\\S]*?)';}
    return part.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  }).join('');
  return {row,keys,pattern:new RegExp('^'+pattern+'$')};
});
export function t(source){
  if(typeof source!=='string'||current==='zh-CN')return source;
  const text=source.trim(),index=locales.indexOf(current);let result=exact.get(text)?.[index];
  if(result===undefined){
    for(const {row,keys,pattern} of patterns){const match=text.match(pattern);if(!match)continue;
      const values=Object.fromEntries(keys.map((key,i)=>[key,match[i+1]]));
      result=row[index].replace(/\{(\w+)\}/g,(_,key)=>['scope','kind','suffix','effort','reason'].includes(key)?t(values[key]):values[key]);break;
    }
  }
  return result===undefined?source:source.slice(0,source.indexOf(text))+result+source.slice(source.indexOf(text)+text.length);
}

// Translate UI chrome only. Document text, model IDs, notes and generated
// answers are data, even if their text happens to match an interface label.
const excluded='script,style,svg,[data-user-content],.textLayer,.original-text,.translated-text:not(.pending):not(.failed),.message .content,.message-images,.chat-image-preview,.image-preview-name,#image-dialog>img,.model-choice,#model-options-connection,#model-status.configured span:nth-child(2),.document-card strong,.outline-item:not([data-ui-outline]),.annotation-card blockquote,.annotation-card p,#note-quote,#selection-context span,#target-language option,#system-language option';
const textSources=new WeakMap(),attributeSources=new WeakMap();
const attributes=['title','placeholder','aria-label','alt'];
function textNode(node){
  if(!node.parentElement||node.parentElement.tagName==='TEXTAREA'||node.parentElement.closest(excluded))return;
  const prior=textSources.get(node),raw=node.nodeValue;
  const source=prior&&raw===prior.output?prior.source:raw,output=t(source);
  // An option without a value would otherwise change its persisted ID.
  const option=node.parentElement;if(option.tagName==='OPTION'&&!option.hasAttribute('value'))option.value=source.trim();
  textSources.set(node,{source,output});if(output!==raw)node.nodeValue=output;
}
function elementAttributes(element){
  if(element.closest(excluded))return;
  const saved=attributeSources.get(element)||{};
  for(const attr of attributes){
    if(!element.hasAttribute(attr))continue;
    const raw=element.getAttribute(attr),prior=saved[attr];
    const source=prior&&raw===prior.output?prior.source:raw,output=t(source);
    saved[attr]={source,output};if(output!==raw)element.setAttribute(attr,output);
  }
  attributeSources.set(element,saved);
}
function localize(root){
  if(root.nodeType===Node.TEXT_NODE){textNode(root);return;}
  if(root.nodeType!==Node.ELEMENT_NODE||root.closest(excluded))return;
  elementAttributes(root);
  const walker=document.createTreeWalker(root,NodeFilter.SHOW_ELEMENT|NodeFilter.SHOW_TEXT,{
    acceptNode:node=>node.nodeType===Node.ELEMENT_NODE&&node.matches(excluded)?NodeFilter.FILTER_REJECT:NodeFilter.FILTER_ACCEPT
  });
  while(walker.nextNode()){const node=walker.currentNode;if(node.nodeType===Node.TEXT_NODE)textNode(node);else elementAttributes(node);}
}
let observer;
export function startI18n(){
  document.documentElement.lang=current;localize(document.head);localize(document.body);
  observer=new MutationObserver(records=>{
    for(const record of records){
      if(record.type==='characterData')textNode(record.target);
      else if(record.type==='attributes')elementAttributes(record.target);
      else for(const node of record.addedNodes)localize(node);
    }
  });
  observer.observe(document.body,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:attributes});
}
export function setLocale(value){
  if(!locales.includes(value))return;
  localStorage.setItem('paperdesk.locale',value);
  current=value;document.documentElement.lang=value;localize(document.head);localize(document.body);
}
