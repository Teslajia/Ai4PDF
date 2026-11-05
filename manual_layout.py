"""Editable page partitions, independent of the original PDF and saved annotations."""
import copy
import hashlib
import json
import math
import re
from collections import defaultdict,deque
import pymupdf as fitz
from translation_policy import page_policy,line_key,normalized


def automatic_blocks(page):
    return [dict(id=f'b{i}',rect=t['rect'],regroup=False,skip=False)
            for i,t in enumerate(t for r in page['rows'] for c in r['columns'] for t in c)]


def page_lines(page,paragraphs,fresh):
    locations=defaultdict(deque)
    for p in fresh:locations[(p['page'],p['text'])].append(p)
    _,kinds,_=page_policy(page)
    result=[]
    for p in paragraphs:
        found=locations[(p['page'],p['text'])]
        match=found.popleft() if found else p
        raw_lines=match.get('_lines',[])
        compact=lambda text:re.sub(r'[\s-]+','',text)
        complete_text=''.join(compact(line_key(line)[1]) for line in raw_lines)
        start=complete_text.find(compact(p['text']));end=start+len(compact(p['text']));offset=0
        for line in raw_lines:
            text=line_key(line)[1]
            length=len(compact(text));lo=max(0,start-offset);hi=min(length,end-offset);offset+=length
            # Long extraction chunks may share a boundary line. Attribute only
            # that chunk's characters; otherwise manual regrouping duplicates prose.
            if start>=0:
                if hi<=lo:continue
                if lo or hi<length:
                    indices=[i for i,c in enumerate(text) if not re.match(r'[\s-]',c)]
                    text=text[indices[lo]:indices[hi-1]+1]
            raw_rect=fitz.Rect(line['bbox'])
            # A vertical margin stamp may cross many automatic slices. It is
            # still rendered, but must not veto editing unrelated body blocks.
            margin_stamp=(abs(line.get('dir',(1,0))[0])<.1 and raw_rect.height>page.cropbox.height*.3
                          and raw_rect.width<raw_rect.height*.15
                          and (raw_rect.x1<page.cropbox.width*.1 or raw_rect.x0>page.cropbox.width*.9))
            rect=raw_rect*page.rotation_matrix
            result.append({'paragraphId':p['id'],'text':text,'rect':list(rect),
                           'protectBoundary':not margin_stamp,
                           'include':p.get('translatable',True) and kinds.get(line_key(line),'text') in ('text','page-marker')})
    return result


def partition_tree(blocks,bounds):
    if len(blocks)==1:
        return {'block':blocks[0]['id']}
    # A continuous horizontal/vertical boundary creates reading-order groups.
    for axis in (0,1):
        candidates=sorted({b['rect'][axis+2] for b in blocks})
        for cut in candidates:
            if cut<=bounds[axis]+.01 or cut>=bounds[axis+2]-.01:continue
            before=[b for b in blocks if b['rect'][axis+2]<=cut+.01]
            after=[b for b in blocks if b['rect'][axis]>=cut-.01]
            if before and after and len(before)+len(after)==len(blocks):
                a=list(bounds);a[axis+2]=cut;b=list(bounds);b[axis]=cut
                return {'direction':'column' if axis==1 else 'row','weights':[cut-bounds[axis],bounds[axis+2]-cut],
                        'children':[partition_tree(before,a),partition_tree(after,b)]}
    raise ValueError('这些分区无法连续排版，请撤销最后一次合并，改为合并同一栏内相邻的块。')


def validate_blocks(value,width,height):
    if not isinstance(value,list) or not 1<=len(value)<=400:
        raise ValueError('每页应有 1–400 个原文块。')
    blocks=[];ids=set()
    for item in value:
        if not isinstance(item,dict):raise ValueError('原文块格式无效。')
        rect=item.get('rect');key=item.get('id')
        if not isinstance(key,str) or not key or len(key)>80 or key in ids:raise ValueError('原文块编号无效。')
        ids.add(key)
        if not isinstance(rect,list) or len(rect)!=4 or not all(type(v) in (int,float) and math.isfinite(v) for v in rect):
            raise ValueError('切分坐标无效。')
        x0,y0,x1,y1=rect
        if x0<0 or y0<0 or x1>width+.01 or y1>height+.01 or x1-x0<.01 or y1-y0<.01:
            raise ValueError('原文块超出页面或尺寸过小。')
        block={'id':key,'rect':[float(v) for v in rect],'regroup':item.get('regroup') is True,'skip':item.get('skip') is True}
        if item.get('text') is not None:
            if not isinstance(item['text'],str) or len(item['text'])>20000:raise ValueError('单块待翻译文字不能超过 20000 字符。')
            block['text']=item['text'].strip()
        blocks.append(block)
    rectangles=[fitz.Rect(b['rect']) for b in blocks]
    if abs(sum(r.get_area() for r in rectangles)-width*height)>.2:
        raise ValueError('切分结果必须完整覆盖原页，不能丢失原文区域。')
    for i,r in enumerate(rectangles):
        if any((r&other).get_area()>.01 for other in rectangles[i+1:]):raise ValueError('原文块重叠，请调整分界。')
    return blocks,partition_tree(blocks,[0,0,width,height])


def center_owner(rect,blocks):
    x=(rect[0]+rect[2])/2;y=(rect[1]+rect[3])/2
    return next((b['id'] for b in blocks if b['rect'][0]<=x<b['rect'][2] and b['rect'][1]<=y<b['rect'][3]),None)


def build_manual_page(page,number,paragraphs,lines,value,previous_blocks=None):
    blocks,tree=validate_blocks(value,page.rect.width,page.rect.height)
    previous=[fitz.Rect(b['rect']) for b in (previous_blocks or [])]
    # Keep each PDF text run whole so selecting/copying from either side remains sound.
    for line in lines:
        if not line.get('protectBoundary',True):continue
        owner=center_owner(line['rect'],blocks)
        if owner is None:continue
        box=fitz.Rect(line['rect'])&page.rect;region=fitz.Rect(next(b['rect'] for b in blocks if b['id']==owner))
        covered=(box&region).get_area()
        prior_covered=max(((box&r).get_area() for r in previous),default=box.get_area())
        # Validate newly introduced clipping, not defects inherited from the
        # automatic layout. A skip/text-only edit must always remain possible.
        if covered<box.get_area()*.97 and covered<prior_covered-.01:
            raise ValueError('分界穿过了文字或公式，请在文字行之间、栏间空白处切分。')
    assignments=defaultdict(list)
    by_pid=defaultdict(list)
    for line in lines:by_pid[line['paragraphId']].append(line)
    for p in paragraphs:
        own=by_pid[p['id']];parts=defaultdict(list)
        for line in own:
            owner=center_owner(line['rect'],blocks)
            if owner is not None:parts[owner].append(line)
        if not parts and p.get('bbox'):
            owner=center_owner(list(fitz.Rect(p['bbox'])*page.rotation_matrix),blocks)
            if owner is not None:parts[owner]=[]
        for owner,part in parts.items():
            complete=len(parts)==1
            text=(p.get('translationSource',p['text']) if complete else normalized('\n'.join(l['text'] for l in part if l['include']))) if p.get('translatable',True) else ''
            assignments[owner].append({'paragraph':p,'complete':complete,'source':text})
    active=[];tiles={}
    for b in blocks:
        entries=assignments[b['id']];eligible=[e for e in entries if e['source']]
        result=[]
        if not b['skip']:
            preserve='text' not in b and all(e['complete'] for e in entries) and (not b['regroup'] or len(eligible)<=1)
            if preserve:
                result=[copy.deepcopy(e['paragraph']) for e in entries]
            else:
                source=b.get('text','\n\n'.join(e['source'] for e in eligible)).strip()
                if source:
                    identity=json.dumps([number,[round(v,3) for v in b['rect']],source],ensure_ascii=False)
                    result=[{'id':f'm{number}-'+hashlib.sha256(identity.encode()).hexdigest()[:20],
                             'page':number,'text':source,'translationSource':source,'translationSourceHash':hashlib.sha256(source.encode()).hexdigest(),
                             'translationKind':'text','translatable':True,'manual':True,
                             'bbox':list(fitz.Rect(b['rect'])*~page.rotation_matrix)}]
        active.extend(result)
        tiles[b['id']]={'rect':b['rect'],'displayRect':b['rect'],'paragraphIds':[p['id'] for p in result],'padding':[.04,.04],'hasGraphics':True}
    def fill(node):
        if 'block' in node:return {'tile':tiles[node['block']]}
        return node|{'children':[fill(c) for c in node['children']]}
    def order(node):
        return node['tile']['paragraphIds'] if 'tile' in node else [pid for child in node['children'] for pid in order(child)]
    filled=fill(tree);by_id={p['id']:p for p in active}
    layout={'page':number,'width':page.rect.width,'height':page.rect.height,'twoColumns':any(n['direction']=='row' for n in walk(tree) if 'direction' in n),
            'manual':True,'tree':filled,'rows':[],'unplacedIds':[]}
    return {'blocks':blocks,'paragraphs':[by_id[pid] for pid in order(filled)],'layout':layout}


def walk(node):
    yield node
    for child in node.get('children',[]):yield from walk(child)


def apply_document(d,manual):
    pages=manual.get('pages',{})
    if pages:
        by_page=defaultdict(list)
        for p in d['paragraphs']:by_page[p['page']].append(p)
        d['translationParagraphs']=[
            p for n in range(1,d['pageCount']+1) for p in (pages[str(n)]['paragraphs'] if str(n) in pages else by_page[n])]
    d['manualPages']=[int(n) for n in pages]
    d['manualRevision']=manual.get('revision','0')
    return d


def apply_layout(automatic,manual):
    return automatic|{'pages':[manual.get('pages',{}).get(str(p['page']),{}).get('layout',p) for p in automatic['pages']],
                      'manualRevision':manual.get('revision','0')}
