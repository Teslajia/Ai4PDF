import io

import pymupdf as fitz
import pytest

from references import build_references, numbers
from test_app import client


def reference_pdf(rotation=0, native=False):
    pdf=fitz.open()
    for _ in range(3):pdf.new_page(width=600,height=800)
    for i in range(2):
        page=pdf[i]
        for j in range(6):
            page.insert_textbox(fitz.Rect(55,70+j*105,545,155+j*105),f'Paragraph {i+1}.{j+1}. We compare prior methods [1] and grouped sources [2, 3]. These results explain the research assumptions and experimental findings in detail.',fontsize=12)
    page=pdf[2];page.insert_text((55,80),'References',fontsize=16)
    for i in range(1,4):page.insert_text((55,180+i*100),f'[{i}] Author {i}. A study of research methods. Journal, 2025.',fontsize=12)
    if native:
        source=pdf[0].search_for('[1]')[0]
        pdf[0].insert_link({'kind':fitz.LINK_GOTO,'from':source,'page':2,'to':fitz.Point(55,280)})
    for page in pdf:page.set_rotation(rotation)
    raw=pdf.tobytes();pdf.close();return raw


@pytest.mark.parametrize('rotation',[0,90,180,270])
def test_reference_index_coordinates_cache_and_original_unchanged(client,rotation):
    raw=reference_pdf(rotation)
    response=client.post('/api/documents',data={'file':(io.BytesIO(raw),'references.pdf')})
    assert response.status_code==200
    url=f"/api/documents/{response.json['id']}"
    result=client.get(url+'/references').json
    assert set(result['entries'])=={'1','2','3'}
    assert len(result['citations']['1'])==12
    assert result['citations']['3']==[]
    with fitz.open(stream=raw,filetype='pdf') as pdf:
        rect=pdf[2].search_for('[1] Author 1. A study of research methods. Journal, 2025.')[0]*pdf[2].rotation_matrix
        entry=result['entries']['1']
        assert entry['page']==3
        assert abs(entry['rect'][1]-rect.y0/pdf[2].rect.height)<.001
    assert client.get(url+'/references').json==result
    assert client.get(url+'/pdf').data==raw


def test_no_numbered_list_guesses_without_bibliography_heading():
    pdf=fitz.open();page=pdf.new_page()
    page.insert_text((50,50),'[1] This is just a numbered instruction, not a reference.')
    assert build_references(pdf)['entries']=={}
    assert numbers('1, 3-5; 8–9, 1')==[1,3,4,5,8,9]
    pdf.close()


def test_bibliography_continuation_at_top_of_right_column():
    pdf=fitz.open();page=pdf.new_page(width=600,height=800)
    for y in [70,120,170]:page.insert_text((30,y),'Ordinary prose in the left column.',fontsize=10)
    page.insert_text((30,450),'References',fontsize=14)
    for i,y in enumerate([500,550,600],1):page.insert_text((30,y),f'[{i}] An author. Article title. Journal 2025.',fontsize=10)
    for i,y in enumerate([70,120,170],4):page.insert_text((320,y),f'[{i}] An author. Article title. Journal 2025.',fontsize=10)
    assert set(build_references(pdf)['entries'])==set('123456')
    pdf.close()
