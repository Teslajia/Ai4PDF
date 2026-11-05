import { Marked } from '/vendor/marked/lib/marked.esm.js';
import DOMPurify from '/vendor/dompurify/dist/purify.es.mjs';
import katex from '/vendor/katex/dist/katex.mjs';

// Tokenize formulas before Markdown consumes \( / \[ or treats TeX underscores
// and asterisks as emphasis. Code spans/fences remain Marked's literal tokens.
function mathToken(source, block=false) {
  const prefix=block?(source.match(/^ {0,3}/)?.[0]||''):'';
  const text=source.slice(prefix.length);
  const delimiters=[['$$','$$',true],['\\[','\\]',true],['\\(','\\)',false],['$','$',false]];
  const pair=delimiters.find(([left,,display])=>text.startsWith(left)&&(!block||display));
  if(!pair)return;
  const [left,right,display]=pair;
  if(left==='$'&&(text[1]==='$'||/\s/.test(text[1]||'')))return;
  let depth=0;
  for(let i=left.length;i<text.length;i++) {
    if(depth<=0&&text.startsWith(right,i)) {
      // Avoid interpreting prices such as "$5 and $10" as math.
      if(left==='$'&&(/\s/.test(text[i-1])||/\d/.test(text[i+1]||'')))return;
      const formula=text.slice(left.length,i);
      if(!formula.trim())return;
      return {type:block?'chatMathBlock':'chatMathInline',raw:prefix+text.slice(0,i+right.length),text:formula,display};
    }
    if(text[i]==='\\')i++;
    else if(text[i]==='{')depth++;
    else if(text[i]==='}')depth--;
    if(left==='$'&&text[i]==='\n')return;
  }
}

export function renderChatMarkdown(element, text) {
  const formulas=[];
  // A per-render nonce prevents raw HTML from impersonating our placeholders.
  const key=`math-${crypto.randomUUID()}`;
  function placeholder(token) {
    const id=formulas.push(token)-1;
    return `<span data-chat-math="${key}-${id}"></span>`+(token.type==='chatMathBlock'?'\n':'');
  }
  const markdown=new Marked({extensions:[
    {name:'chatMathBlock',level:'block',
      start:source=>source.search(/^ {0,3}(?:\$\$|\\\[)/m),
      tokenizer:source=>mathToken(source,true),renderer:placeholder},
    {name:'chatMathInline',level:'inline',
      start:source=>source.search(/\$|\\[([]/),
      tokenizer(source){if(!this.lexer.state.inRawBlock)return mathToken(source);},renderer:placeholder}
  ]});
  element.innerHTML=DOMPurify.sanitize(markdown.parse(text),{FORBID_TAGS:['img','style','iframe','form','input']});
  for(const [index,formula] of formulas.entries()) {
    const node=element.querySelector(`[data-chat-math="${key}-${index}"]`);
    if(!node)continue;
    node.classList.add('chat-math');
    node.classList.toggle('chat-math-display',formula.display);
    try {
      katex.render(formula.text,node,{displayMode:formula.display,throwOnError:true,trust:false,strict:'ignore',maxExpand:1000,maxSize:20});
    } catch {
      // A partial stream or invalid model-produced TeX must not break the reply.
      node.textContent=formula.raw;node.classList.add('chat-math-fallback');
    }
    node.removeAttribute('data-chat-math');
  }
}
