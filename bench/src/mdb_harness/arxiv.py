"""Bounded arXiv search and public preprint text, with persistent query caching."""
import io
import re
import time
from xml.etree import ElementTree as ET

import requests


def collect_arxiv(store,queries,rows=5,max_full_texts=2):
    from pypdf import PdfReader
    session=requests.Session();session.headers['User-Agent']='LatticeMaterialsResearch/0.2'
    ns={'a':'http://www.w3.org/2005/Atom'};opened=0;last=0
    for query in queries:
        opened_here=0
        prior=store.db.execute("SELECT 1 FROM queries WHERE provider='arxiv' AND query=? AND status='ok' AND retrieved_at>datetime('now','-7 days')",(query,)).fetchone()
        if prior:continue
        terms=re.findall(r'[A-Za-z0-9]+',query)[:4]
        search='cat:cond-mat.* AND '+' AND '.join('all:"'+t+'"' for t in terms)
        try:
            time.sleep(max(0,3-(time.monotonic()-last)));last=time.monotonic()
            response=session.get('https://export.arxiv.org/api/query',params={'search_query':search,'max_results':rows},timeout=25)
            response.raise_for_status();root=ET.fromstring(response.content)
            entries=root.findall('a:entry',ns)
            for item in entries:
                title=' '.join((item.findtext('a:title','',ns)).split())
                url=item.findtext('a:id','',ns).replace('http://','https://')
                identifier=url.rsplit('/abs/',1)[-1]
                if not re.fullmatch(r'(?:[a-z.-]+/)?[0-9.]+v?\d*',identifier):continue
                abstract=item.findtext('a:summary','',ns)
                store.add(title,url,'abstract_preprint',[('title and abstract',title+'\n'+abstract)])
                if opened>=max_full_texts or opened_here>=1:continue
                try:
                    pdf_url='https://arxiv.org/pdf/'+identifier
                    with session.get(pdf_url,timeout=30,stream=True) as pdf:
                        pdf.raise_for_status();data=bytearray()
                        for chunk in pdf.iter_content(65536):
                            data.extend(chunk)
                            if len(data)>12_000_000:raise ValueError('Paper exceeds download budget')
                    reader=PdfReader(io.BytesIO(data))
                    sections=[(f'page {i+1}',page.extract_text() or '') for i,page in enumerate(reader.pages[:80])]
                    if any(t.strip() for _,t in sections):
                        store.add(title,pdf_url,'full_text_preprint',sections);opened+=1;opened_here+=1
                except Exception as exc:
                    store.query_log('arxiv_pdf',identifier,'unavailable',{'error_type':type(exc).__name__})
            store.query_log('arxiv',query,'ok',{'returned':len(entries),'scope':'Bounded condensed-matter preprint search; peer review and exact-phase relevance not established'})
        except (requests.RequestException,ET.ParseError,ValueError) as exc:
            store.query_log('arxiv',query,'error',{'error_type':type(exc).__name__})
    return {'full_texts_added':opened}
