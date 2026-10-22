"""Local evidence ledger: source hashes, retrieval coverage and quote validation."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from xml.etree import ElementTree

import requests


def now():
    return datetime.now(timezone.utc).isoformat()


class EvidenceStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path=path
        self.db=sqlite3.connect(path,timeout=60)
        self.batch_mode=False
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=NORMAL')
        self.db.row_factory=sqlite3.Row
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY,title TEXT,url TEXT,kind TEXT,sha256 TEXT,retrieved_at TEXT);
        CREATE TABLE IF NOT EXISTS chunks(id TEXT PRIMARY KEY,source_id TEXT,locator TEXT,text TEXT);
        CREATE TABLE IF NOT EXISTS queries(id INTEGER PRIMARY KEY,provider TEXT,query TEXT,status TEXT,details TEXT,retrieved_at TEXT);
        ''')
        indexed=self.db.execute("SELECT 1 FROM sqlite_master WHERE name='chunks_fts'").fetchone()
        self.db.executescript('''
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(text,content='chunks',content_rowid='rowid',tokenize='unicode61');
        CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
            INSERT INTO chunks_fts(rowid,text) VALUES(new.rowid,new.text);
        END;
        CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
            INSERT INTO chunks_fts(chunks_fts,rowid,text) VALUES('delete',old.rowid,old.text);
        END;
        CREATE INDEX IF NOT EXISTS source_url ON sources(url);
        CREATE INDEX IF NOT EXISTS chunk_source ON chunks(source_id);
        CREATE TABLE IF NOT EXISTS memory_notes(id TEXT PRIMARY KEY,campaign TEXT,candidate TEXT,kind TEXT,text TEXT,evidence_ids TEXT,created_at TEXT);
        CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(text,content='memory_notes',content_rowid='rowid');
        CREATE TRIGGER IF NOT EXISTS notes_ai AFTER INSERT ON memory_notes BEGIN
            INSERT INTO notes_fts(rowid,text) VALUES(new.rowid,new.text);
        END;
        CREATE TABLE IF NOT EXISTS imports(name TEXT PRIMARY KEY,manifest TEXT,status TEXT,records INTEGER);
        ''')
        if not indexed:
            self.db.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')");self.db.commit()

    def add(self,title,url,kind,sections):
        raw=json.dumps(sections,sort_keys=True,ensure_ascii=False)
        digest=hashlib.sha256(raw.encode()).hexdigest()
        sid=hashlib.sha256((url+kind+digest).encode()).hexdigest()[:16]
        self.db.execute('INSERT OR IGNORE INTO sources VALUES(?,?,?,?,?,?)',(sid,title,url,kind,digest,now()))
        for section_index,(locator,text) in enumerate(sections):
            text=' '.join(text.split())
            for start in range(0,len(text),2200):
                chunk=text[start:start+2600]
                cid=f'{sid}:{section_index}:{start}'
                self.db.execute('INSERT OR IGNORE INTO chunks VALUES(?,?,?,?)',(cid,sid,locator,chunk))
        if not self.batch_mode: self.db.commit()
        return sid

    def query_log(self,provider,query,status,details):
        with self.db:
            self.db.execute('INSERT INTO queries(provider,query,status,details,retrieved_at) VALUES(?,?,?,?,?)',
                            (provider,query,status,json.dumps(details),now()))

    def local_file(self,path:Path):
        if path.suffix.lower()=='.pdf':
            from pypdf import PdfReader
            sections=[(f'page {i+1}',page.extract_text() or '') for i,page in enumerate(PdfReader(path).pages)]
        else:
            sections=[('local document',path.read_text())]
        if not any(text.strip() for _,text in sections):
            raise ValueError(f'No extractable text in {path}; OCR is not implemented')
        return self.add(path.name,path.resolve().as_uri(),'full_text_local',sections)

    def retrieve(self,query,limit=12,max_characters=20000,elements=None):
        # Inverted index + BM25 avoids scanning the entire literature on each prompt.
        stop={'the','and','with','for','from','that','this','material','materials','new','of','to','in'}
        terms=list(dict.fromkeys(t for t in re.findall(r'[a-z0-9]{2,}',query.lower()) if t not in stop))[:24]
        if not terms:return []
        expression=' OR '.join('"'+term+'"' for term in terms)
        if elements:
            # Require explicit chemical-system mentions. This establishes relevance,
            # never support for a particular phase or physical mechanism.
            from pymatgen.core import Element
            aliases={'B':['boron','boride'],'C':['carbon','carbide','diamond'],'N':['nitrogen','nitride'],
                     'Si':['silicon','silicide'],'Al':['aluminum','aluminium','aluminate'],'O':['oxygen','oxide']}
            groups=['('+' OR '.join('"'+a+'"' for a in aliases.get(e,[Element(e).long_name.lower()]))+')' for e in sorted(set(elements))]
            families={frozenset(['Al','N']):['aln','aluminum nitride','aluminium nitride'],
                      frozenset(['Si','N']):['si3n4','silicon nitride'],frozenset(['Si','C']):['sic','silicon carbide'],
                      frozenset(['B','N']):['bn','hbn','cbn','boron nitride'],
                      frozenset(['B','Si','N']):['boron silicon nitride','bsin','sibn'],
                      frozenset(['B','C','N']):['boron carbon nitride','bcn']}
            formulas=list(families.get(frozenset(elements),[]))
            from pymatgen.core import Composition
            for token in re.findall(r'(?<![A-Za-z])(?:[A-Z][a-z]?\d*)+(?![A-Za-z])',query):
                try:
                    if {e.symbol for e in Composition(token).elements}==set(elements):formulas.append(token.lower())
                except ValueError:pass
            expression='('+' AND '.join(groups)+')'+''.join(' OR "'+f+'"' for f in formulas)
            topics=[t for t in terms if t in {'phonon','phonons','stability','dielectric','thermal','conductivity','electronic','bonding','metastability'}]
            if topics:expression='('+expression+') AND ('+' OR '.join('"'+t+'"' for t in topics)+')'
        rows=self.db.execute('''SELECT c.*,s.title,s.url,s.kind,bm25(chunks_fts) AS rank
            FROM chunks_fts JOIN chunks c ON c.rowid=chunks_fts.rowid JOIN sources s ON s.id=c.source_id
            WHERE chunks_fts MATCH ? ORDER BY rank LIMIT ?''',(expression,min(300,max(30,limit*8)))).fetchall()
        result=[];counts={};characters=0
        # Diversity prevents one long review article consuming the whole context.
        for row in rows:
            if counts.get(row['source_id'],0)>=2: continue
            if characters+len(row['text'])>max_characters: continue
            counts[row['source_id']]=counts.get(row['source_id'],0)+1
            result.append({**dict(row),'relevance':'chemical_system_mentions_not_phase_validation' if elements else 'keyword_retrieval_unverified'});characters+=len(row['text'])
            if len(result)>=limit:break
        return result

    def import_sources(self,other,source_ids):
        for sid in dict.fromkeys(source_ids):
            source=other.db.execute('SELECT * FROM sources WHERE id=?',(sid,)).fetchone()
            if not source:continue
            with self.db:
                self.db.execute('INSERT OR IGNORE INTO sources VALUES(?,?,?,?,?,?)',tuple(source))
                for row in other.db.execute('SELECT * FROM chunks WHERE source_id=?',(sid,)):
                    self.db.execute('INSERT OR IGNORE INTO chunks VALUES(?,?,?,?)',tuple(row))

    def remember(self,campaign,candidate,kind,text,evidence_ids=()):
        identity=hashlib.sha256(json.dumps([campaign,candidate,kind,text]).encode()).hexdigest()[:24]
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO memory_notes VALUES(?,?,?,?,?,?,?)',
                            (identity,campaign,candidate,kind,text,json.dumps(list(evidence_ids)),now()))

    def recall(self,query,limit=6):
        terms=list(dict.fromkeys(re.findall(r'[a-z0-9]{2,}',query.lower())))[:16]
        if not terms:return []
        rows=self.db.execute('''SELECT n.* FROM notes_fts JOIN memory_notes n ON n.rowid=notes_fts.rowid
            WHERE notes_fts MATCH ? ORDER BY bm25(notes_fts) LIMIT ?''',(' OR '.join('"'+x+'"' for x in terms),limit))
        return [{**dict(row),'warning':'Prior computational research memory; not independent literature evidence'} for row in rows]

    def stats(self):
        return {'sources':self.db.execute('SELECT count(*) FROM sources').fetchone()[0],
                'chunks':self.db.execute('SELECT count(*) FROM chunks').fetchone()[0],
                'full_text_sources':self.db.execute("SELECT count(*) FROM sources WHERE kind LIKE 'full_text%'").fetchone()[0],
                'research_notes':self.db.execute('SELECT count(*) FROM memory_notes').fetchone()[0],
                'retrieval':'SQLite FTS5 / BM25 with source diversity and bounded context'}

    def validate_citation(self,citation):
        row=self.db.execute('SELECT c.*,s.kind FROM chunks c JOIN sources s ON s.id=c.source_id WHERE c.id=?',(citation.chunk_id,)).fetchone()
        if row is None or row['source_id']!=citation.source_id:
            return {'valid':False,'full_text':False,'reason':'Unknown source/chunk identity'}
        quote=' '.join(citation.quote.split())
        valid=quote in row['text']
        return {'valid':valid,'full_text':row['kind'].startswith('full_text'),
                'reason':'Exact quote found; entailment still needs review' if valid else 'Quoted text is absent from source chunk'}

    def sources(self):
        return [dict(row) for row in self.db.execute('SELECT * FROM sources')]

    def coverage(self):
        return [dict(row) for row in self.db.execute('SELECT * FROM queries ORDER BY id')]

    def close(self):
        self.db.close()


def collect_literature(store:EvidenceStore,queries:list[str],*,rows=5,max_open_papers=4):
    from .arxiv import collect_arxiv
    preprints=collect_arxiv(store,queries,rows=rows,max_full_texts=min(8,max_open_papers))
    session=requests.Session()
    session.headers['User-Agent']='IndependentMaterialsDiscovery/0.1 (research evidence retrieval)'
    opened=preprints['full_texts_added']
    for query in queries:
        try:
            response=session.get('https://api.crossref.org/works',params={'query':query,'rows':rows},timeout=25)
            response.raise_for_status()
            items=response.json()['message']['items']
            for item in items:
                title=' '.join(item.get('title',[]))
                abstract=re.sub('<[^>]+>',' ',item.get('abstract',''))
                store.add(title,item.get('URL','https://doi.org/'+item.get('DOI','')),
                          'abstract' if abstract else 'metadata', [('abstract' if abstract else 'title',abstract or title)])
            store.query_log('crossref',query,'ok',{'returned':len(items),'scope':'bounded metadata/abstract search; not a novelty verdict'})
        except (requests.RequestException,ValueError,KeyError) as exc:
            store.query_log('crossref',query,'error',{'error_type':type(exc).__name__})
        if opened>=max_open_papers:
            continue
        try:
            response=session.get('https://www.ebi.ac.uk/europepmc/webservices/rest/search',
                                 params={'query':query+' OPEN_ACCESS:Y','format':'json','pageSize':rows,'resultType':'core'},timeout=25)
            response.raise_for_status()
            items=response.json().get('resultList',{}).get('result',[])
            store.query_log('europepmc',query,'ok',{'returned':len(items),'scope':'open-access subset'})
            for item in items:
                pmcid=item.get('pmcid')
                if not pmcid or opened>=max_open_papers:
                    continue
                url=f'https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML'
                xml=session.get(url,timeout=25)
                xml.raise_for_status()
                root=ElementTree.fromstring(xml.content)
                sections=[]
                for index,section in enumerate(root.findall('.//body//sec')):
                    # Paragraphs directly in the section avoid counting nested text twice.
                    text=' '.join(' '.join(p.itertext()) for p in section.findall('./p'))
                    if text.strip():
                        sections.append((section.findtext('title') or f'section {index+1}',text))
                if sections:
                    store.add(item.get('title',pmcid),url,'full_text_open_access',sections)
                    opened+=1
        except (requests.RequestException,ValueError,KeyError,ElementTree.ParseError) as exc:
            store.query_log('europepmc',query,'error',{'error_type':type(exc).__name__})
    return {'sources':store.stats()['sources'],'open_papers_downloaded':opened,'coverage':store.coverage()}
