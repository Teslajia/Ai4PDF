"""Diagram labels must not move the gutter into a column of prose."""
import io

import pymupdf as fitz

import app as server
from test_app import client


def diagram_above_columns():
    pdf = fitz.open()
    page = pdf.new_page(width=612, height=792)
    # A full-width diagram with long text labels at irregular x coordinates.
    # These four right-hand boxes outvote the two genuine right paragraphs.
    page.draw_rect((48, 50, 564, 302), color=(.2, .5, .3), fill=(.92, .96, .91))
    for x, y in [(90, 65), (150, 125), (90, 185), (150, 245),
                 (452, 65), (470, 125), (452, 185), (470, 245)]:
        spare = page.insert_textbox((x, y, x+85, y+53), 'Diagram label explains detailed image content and multiple visual restoration steps.', fontsize=6)
        assert spare >= 0
    page.insert_textbox((48, 316, 564, 345), 'Figure 1. A wide diagram contains explanatory labels. Its artwork stays together above the two independent text columns.', fontsize=9)
    for x in (48, 312):
        for y in (375, 530):
            page.insert_textbox((x, y, x+252, y+130),
                'This body paragraph describes the research method and its results. '
                'The text occupies a regular column and must remain separate from the neighboring column. '
                'Each paragraph needs its own translation immediately below its original text. ' * 2, fontsize=10)
    content = pdf.tobytes()
    pdf.close()
    return content


def assert_body_columns(layout, paragraphs):
    page = layout['pages'][0]
    body_ids = {p['id'] for p in paragraphs if p['bbox'][1] > 350}
    tiles = [tile for row in page['rows'] for column in row['columns'] for tile in column]
    body_tiles = [tile for tile in tiles if body_ids.intersection(tile['paragraphIds'])]
    assert page['twoColumns']
    assert len(body_tiles) == 4
    assert all(len(set(tile['paragraphIds']) & body_ids) == 1 for tile in body_tiles)
    for tile in body_tiles:
        box = fitz.Rect(tile['rect'])
        assert box.x1 <= 310 or box.x0 >= 302, box
    assert {pid for tile in body_tiles for pid in tile['paragraphIds']} == body_ids
    assert abs(sum(fitz.Rect(tile['rect']).get_area() for tile in tiles)-612*792) < .1
    for i, tile in enumerate(tiles):
        for other in tiles[i+1:]:
            assert (fitz.Rect(tile['rect']) & fitz.Rect(other['rect'])).get_area() < .01
    assert any(fitz.Rect(tile['rect']).width == 612 and tile['hasGraphics'] for tile in tiles)


def test_diagram_text_does_not_shift_body_gutter(client):
    content = diagram_above_columns()
    response = client.post('/api/documents', data={'file': (io.BytesIO(content), 'diagram-columns.pdf')})
    assert response.status_code == 200
    doc = response.json
    assert any(p.get('translationKind') == 'figure' and len(p['text']) > 70 for p in doc['paragraphs'])
    result = client.get(f"/api/documents/{doc['id']}/layout")
    assert result.status_code == 200
    assert_body_columns(result.json, doc['paragraphs'])


def test_old_layout_cache_refreshes_without_changing_saved_data(client):
    content = diagram_above_columns()
    doc = client.post('/api/documents', data={'file': (io.BytesIO(content), 'old-library.pdf')}).json
    folder = server.folder(doc['id'])
    paragraphs = doc['paragraphs']
    body = next(p for p in paragraphs if p['bbox'][1] > 350)
    state = server.state(doc['id'])
    state['translations']['简体中文:'+body['id']] = 'Keep the existing translation.'
    state['annotations'] = [{'id': 'retained-note', 'page': 1, 'kind': 'note', 'note': 'Keep the note.'}]
    server.write_json(folder/'state.json', state)
    old = client.get(f"/api/documents/{doc['id']}/layout").json
    old['version'] = 9
    old['pages'][0]['rows'] = [{'columns': [[{'rect': [0, 0, 612, 792], 'displayRect': [0, 0, 612, 792],
                                           'paragraphIds': [p['id'] for p in paragraphs], 'hasGraphics': True, 'padding': [.04, .04]}]]}]
    server.write_json(folder/'layout.json', old)
    before = {name: (folder/name).read_bytes() for name in ('original.pdf', 'document.json', 'state.json')}
    refreshed = client.get(f"/api/documents/{doc['id']}/layout").json
    assert refreshed['version'] > 9
    assert_body_columns(refreshed, paragraphs)
    assert {name: (folder/name).read_bytes() for name in before} == before
    assert [p['id'] for p in client.get(f"/api/documents/{doc['id']}").json['paragraphs']] == [p['id'] for p in paragraphs]
