"""Create a small real PDF for the welcome screen and integration tests."""
from pathlib import Path
import pymupdf as fitz

ROOT = Path(__file__).resolve().parents[1]


def create_sample(path):
    pdf = fitz.open()
    titles = ['A quieter way to read research', 'From reading to understanding', 'Keep the ideas that matter']
    sections = [
        [('Abstract', 'Reading a research paper is more than moving through pages. It is a conversation with the ideas on the page. This sample document introduces a local reading workspace that brings the original paper, personal annotations, bilingual translation and an AI assistant into one place.'),
         ('1. A workspace for your curiosity', 'Ai4PDF keeps the original PDF on the left and an assistant on the right. You can open a document from your computer, browse its pages and return to the same reading position later. The original layout stays intact, including figures, equations and references.'),
         ('2. Read actively', 'Select a few words in this paragraph to try highlighting. The selection toolbar also lets you add an underline, write a note or send the passage to the assistant. Your annotations are saved locally and can be exported as native PDF annotations.'),
         ('3. Bring your own model', 'The assistant connects to an API endpoint and model that you choose. A local service forwards requests to an OpenAI-compatible Chat Completions endpoint. The application does not contain a shared model account or a preconfigured API key.')],
        [('4. Translation in context', 'Switch to the bilingual view to read each original paragraph followed by its translation. Translation runs one paragraph at a time, so you can pause and resume without losing completed work. A failed request does not erase the paragraphs already translated.'),
         ('5. Questions that deepen understanding', 'A useful question distinguishes what a paper claims from the evidence it provides. Ask the assistant to identify assumptions, explain the method, compare experimental results or discuss limitations. Page references help you return to the original text and check the answer.'),
         ('6. Working with long documents', 'Short documents can fit in the model context in full. For longer documents, this application selects a limited set of passages. The assistant is informed when its context is partial. Selecting the passage you care about is a practical way to focus the conversation.'),
         ('A small experiment', 'Highlight this sentence, add a note, and export the document. Open the exported file in another PDF reader. The highlight and its comment should remain available as standard PDF annotations, while the original file remains unchanged.')],
        [('7. Local files, explicit connections', 'The document library, annotations, translation cache and conversations are stored on this computer. PDF rendering does not require an external CDN. Using the assistant or translation sends the relevant text to the API provider selected in settings.'),
         ('8. Know the limits', 'An image-only scan contains no selectable text until optical character recognition is performed. Complex mathematical notation, tables and unusual column layouts may not extract cleanly. The original PDF is always the reference for layout, figures and exact wording.'),
         ('9. Make room for the next idea', 'Good notes do not need to be long. Capture the claim, the evidence and the question it leaves you with. Over time, these small observations become a record of how your understanding developed.'),
         ('Reading checklist', 'Identify the main research question. Locate the central result. Examine the method and its assumptions. Check which evidence supports each claim. Write down one limitation and one follow-up question.')]
    ]
    for i, (title, chunks) in enumerate(zip(titles, sections)):
        page = pdf.new_page(width=595,height=842)
        page.draw_rect(fitz.Rect(0,0,595,9), color=None, fill=(.15,.40,.32))
        page.insert_text((55,53), 'Ai4PDF   /   R E A D I N G   N O T E S', fontsize=8, color=(.40,.53,.43))
        page.insert_textbox(fitz.Rect(55,89,540,157),title,fontname='tiro',fontsize=28,color=(.17,.28,.21))
        page.insert_text((55,172), f'A practical introduction   |   Sample document   |   {i+1:02d}', fontsize=9,color=(.5,.55,.47))
        page.draw_line((55,193),(540,193),color=(.82,.86,.79),width=.6)
        y=220
        for heading,text in chunks:
            page.insert_text((55,y),heading,fontname='hebo',fontsize=11,color=(.19,.36,.25))
            result=page.insert_textbox(fitz.Rect(55,y+14,540,y+113),text,fontname='tiro',fontsize=11,lineheight=1.45,color=(.27,.31,.25))
            assert result >= 0, 'Sample text overflows'
            y+=137
        page.insert_text((55,811),'YOUR PAPERS. YOUR PERSPECTIVE.',fontsize=7,color=(.57,.63,.52))
        page.insert_text((525,811),str(i+1),fontsize=9,color=(.4,.5,.4))
    pdf.set_metadata({'title':'A quieter way to read research','author':'Ai4PDF','subject':'Local reading workspace demo'})
    pdf.set_toc([[1,t,i+1] for i,t in enumerate(titles)])
    pdf.save(path)
    pdf.close()


if __name__=='__main__':
    create_sample(ROOT/'static'/'sample.pdf')
