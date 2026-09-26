"""Veyra local inventory service. SQLite transactions serialize writers (BEGIN IMMEDIATE)."""
import json
import os
import secrets
import sqlite3
import hashlib
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

DB = os.environ.get('VEYRA_DB', str(Path(__file__).with_name('veyra.sqlite3')))
SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, salt TEXT NOT NULL, hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS categories(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY, sku TEXT UNIQUE NOT NULL, name TEXT NOT NULL, category_id INTEGER REFERENCES categories(id), uom TEXT NOT NULL DEFAULT 'unit', reorder_point INTEGER NOT NULL DEFAULT 0 CHECK(reorder_point>=0));
CREATE TABLE IF NOT EXISTS warehouses(id INTEGER PRIMARY KEY, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS locations(id INTEGER PRIMARY KEY, warehouse_id INTEGER NOT NULL REFERENCES warehouses(id), code TEXT NOT NULL, name TEXT NOT NULL, UNIQUE(warehouse_id,code));
CREATE TABLE IF NOT EXISTS stock(product_id INTEGER NOT NULL REFERENCES products(id), location_id INTEGER NOT NULL REFERENCES locations(id), qty INTEGER NOT NULL DEFAULT 0 CHECK(qty>=0), version INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(product_id,location_id));
CREATE TABLE IF NOT EXISTS movements(id INTEGER PRIMARY KEY, ref TEXT UNIQUE NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('RECEIVE','DELIVER','TRANSFER','ADJUST')), product_id INTEGER NOT NULL REFERENCES products(id), source_id INTEGER REFERENCES locations(id), dest_id INTEGER REFERENCES locations(id), qty INTEGER NOT NULL, source_version INTEGER, dest_version INTEGER, actor INTEGER NOT NULL REFERENCES users(id), contact TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS count_sessions(id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id), location_id INTEGER NOT NULL REFERENCES locations(id), captured_version INTEGER NOT NULL, captured_qty INTEGER NOT NULL, actor INTEGER NOT NULL REFERENCES users(id), started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, status TEXT NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN','SUBMITTED','CANCELED')));
CREATE TABLE IF NOT EXISTS evidence(id INTEGER PRIMARY KEY, session_id INTEGER UNIQUE NOT NULL REFERENCES count_sessions(id), product_id INTEGER NOT NULL REFERENCES products(id), location_id INTEGER NOT NULL REFERENCES locations(id), observed_qty INTEGER NOT NULL CHECK(observed_qty>=0), captured_version INTEGER NOT NULL, actor INTEGER NOT NULL REFERENCES users(id), status TEXT NOT NULL, submitted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS resolutions(id INTEGER PRIMARY KEY, evidence_id INTEGER NOT NULL UNIQUE REFERENCES evidence(id), movement_ref TEXT NOT NULL UNIQUE REFERENCES movements(ref), note TEXT NOT NULL, actor INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS deliveries(ref TEXT PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id), location_id INTEGER NOT NULL REFERENCES locations(id), qty INTEGER NOT NULL CHECK(qty>0), contact TEXT, state TEXT NOT NULL CHECK(state IN ('PENDING','DONE','CANCELED')), actor INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS decisions(id INTEGER PRIMARY KEY, ref TEXT NOT NULL REFERENCES deliveries(ref), stage TEXT NOT NULL CHECK(stage IN ('PREFLIGHT','COMMIT')), status TEXT NOT NULL, reason TEXT NOT NULL, evidence_version INTEGER, current_version INTEGER NOT NULL, evidence_id INTEGER REFERENCES evidence(id), stock_qty INTEGER NOT NULL, actor INTEGER NOT NULL REFERENCES users(id), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS ix_movements_product ON movements(product_id,created_at);
CREATE INDEX IF NOT EXISTS ix_evidence_scope ON evidence(product_id,location_id,captured_version);
"""

class Failure(Exception):
    def __init__(self, code, status=400):
        self.code, self.status = code, status
        super().__init__(code)

def text(v, key, maxlen=120):
    if not isinstance(v, str) or not v.strip() or len(v) > maxlen:
        raise Failure('INVALID_'+key.upper())
    return v.strip()

def integer(v, key, minimum=0):
    if type(v) is not int or v < minimum or v > 1000000000:
        raise Failure('INVALID_'+key.upper())
    return v

def connect():
    db = sqlite3.connect(DB, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA busy_timeout=15000')
    return db

def init():
    db=connect()
    try: db.executescript(SCHEMA)
    finally: db.close()

@contextmanager
def transaction():
    db = connect()
    try:
        db.execute('BEGIN IMMEDIATE')
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

def rows(db, sql, args=()):
    return [dict(r) for r in db.execute(sql, args).fetchall()]

def one(db, sql, args=()):
    r = db.execute(sql, args).fetchone()
    return dict(r) if r else None

def scope(db, sku, location):
    p = one(db, 'SELECT * FROM products WHERE sku=?', (text(sku,'sku'),))
    l = one(db, 'SELECT l.*,w.code warehouse FROM locations l JOIN warehouses w ON w.id=l.warehouse_id WHERE l.code=? OR (w.code || "/" || l.code)=?', (location,location)) if isinstance(location,str) else None
    if not p or not l:
        raise Failure('INVALID_SKU_OR_LOCATION',404)
    # unqualified codes must be unique across warehouses
    if '/' not in location and one(db,'SELECT COUNT(*) n FROM locations WHERE code=?',(location,))['n'] > 1:
        raise Failure('AMBIGUOUS_LOCATION')
    db.execute('INSERT OR IGNORE INTO stock(product_id,location_id) VALUES(?,?)',(p['id'],l['id']))
    s = one(db,'SELECT * FROM stock WHERE product_id=? AND location_id=?',(p['id'],l['id']))
    return p,l,s

def auth(db, token):
    s = one(db,'SELECT user_id FROM sessions WHERE token=? AND expires>?',(token or '',int(time.time())))
    if not s: raise Failure('UNAUTHORIZED',401)
    return s['user_id']

def password_hash(password,salt):
    return hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()

def login(db, data, signup=False):
    username = text(data.get('username'), 'username',40)
    password = text(data.get('password'), 'password',256)
    if signup:
        if len(username)<3 or len(password)<8: raise Failure('WEAK_CREDENTIALS')
        salt=secrets.token_hex(16)
        db.execute('INSERT INTO users(username,salt,hash) VALUES(?,?,?)',(username,salt,password_hash(password,salt)))
    u=one(db,'SELECT * FROM users WHERE username=?',(username,))
    if not u or not secrets.compare_digest(u['hash'],password_hash(password,u['salt'])):
        raise Failure('INVALID_CREDENTIALS',401)
    token=secrets.token_urlsafe(32)
    db.execute('INSERT INTO sessions VALUES(?,?,?)',(token,u['id'],int(time.time())+86400))
    return {'token':token,'username':username}

def create(db, table, data):
    if table=='categories':
        name=text(data.get('name'),'name'); db.execute('INSERT INTO categories(name) VALUES(?)',(name,))
    elif table=='warehouses':
        db.execute('INSERT INTO warehouses(code,name) VALUES(?,?)',(text(data.get('code'),'code',30),text(data.get('name'),'name')))
    elif table=='locations':
        w=one(db,'SELECT id FROM warehouses WHERE code=?',(text(data.get('warehouse'),'warehouse'),))
        if not w: raise Failure('INVALID_WAREHOUSE',404)
        db.execute('INSERT INTO locations(warehouse_id,code,name) VALUES(?,?,?)',(w['id'],text(data.get('code'),'code',30),text(data.get('name'),'name')))
    elif table=='products':
        category=data.get('category')
        c=one(db,'SELECT id FROM categories WHERE name=?',(category,)) if category else None
        if category and not c: raise Failure('INVALID_CATEGORY',404)
        db.execute('INSERT INTO products(sku,name,category_id,uom,reorder_point) VALUES(?,?,?,?,?)',(text(data.get('sku'),'sku',60),text(data.get('name'),'name'),c['id'] if c else None,text(data.get('uom','unit'),'uom',30),integer(data.get('reorder_point',0),'reorder_point')))
    else: raise Failure('INVALID_RESOURCE',404)
    return {'status':'CREATED'}

def update_product(db,data):
    sku=text(data.get('sku'),'sku',60)
    p=one(db,'SELECT id FROM products WHERE sku=?',(sku,))
    if not p: raise Failure('INVALID_SKU',404)
    changes={}
    for key in ('name','uom'):
        if key in data: changes[key]=text(data[key],key,120 if key=='name' else 30)
    if 'reorder_point' in data: changes['reorder_point']=integer(data['reorder_point'],'reorder_point')
    if 'category' in data:
        c=one(db,'SELECT id FROM categories WHERE name=?',(text(data['category'],'category'),))
        if not c: raise Failure('INVALID_CATEGORY',404)
        changes['category_id']=c['id']
    if not changes: raise Failure('NO_CHANGES')
    db.execute('UPDATE products SET '+','.join(k+'=?' for k in changes)+' WHERE id=?',(*changes.values(),p['id']))
    return {'status':'UPDATED','sku':sku}

def stock_change(db,p,l,delta):
    s=one(db,'SELECT * FROM stock WHERE product_id=? AND location_id=?',(p['id'],l['id']))
    if not s:
        db.execute('INSERT INTO stock(product_id,location_id) VALUES(?,?)',(p['id'],l['id']))
        s={'qty':0,'version':0}
    if s['qty']+delta<0: raise Failure('INSUFFICIENT_STOCK',409)
    db.execute('UPDATE stock SET qty=qty+?,version=version+1 WHERE product_id=? AND location_id=?',(delta,p['id'],l['id']))
    return s['version']+1

def movement(db, data, actor):
    kind=text(data.get('kind'),'kind').upper()
    if kind not in ('RECEIVE','TRANSFER','ADJUST'): raise Failure('INVALID_MOVEMENT_KIND')
    ref=text(data.get('ref'),'ref',80)
    if one(db,'SELECT id FROM movements WHERE ref=?',(ref,)) or one(db,'SELECT ref FROM deliveries WHERE ref=?',(ref,)):
        raise Failure('DUPLICATE_REFERENCE',409)
    p,l,s=scope(db,data.get('sku'),data.get('location'))
    contact=data.get('contact')
    if contact is not None: contact=text(contact,'contact')
    qty=integer(data.get('qty'),'qty',1) if kind!='ADJUST' else integer(data.get('qty'),'qty')
    if kind=='RECEIVE':
        sv=None; dv=stock_change(db,p,l,qty); src=None; dest=l['id']
    elif kind=='TRANSFER':
        target=data.get('destination'); p2,l2,_=scope(db,p['sku'],target)
        if l['id']==l2['id']: raise Failure('SAME_LOCATION')
        sv=stock_change(db,p,l,-qty); dv=stock_change(db,p,l2,qty); src=l['id']; dest=l2['id']
    else:
        # adjustment is explicit, never triggered by submitting evidence
        sv=stock_change(db,p,l,qty-s['qty']); dv=None; src=l['id']; dest=None
    db.execute('INSERT INTO movements(ref,kind,product_id,source_id,dest_id,qty,source_version,dest_version,actor,contact) VALUES(?,?,?,?,?,?,?,?,?,?)',(ref,kind,p['id'],src,dest,qty,sv,dv,actor,contact))
    return {'status':'DONE','ref':ref,'source_version':sv,'dest_version':dv}

def start_count(db,data,actor):
    p,l,s=scope(db,data.get('sku'),data.get('location'))
    cur=db.execute('INSERT INTO count_sessions(product_id,location_id,captured_version,captured_qty,actor) VALUES(?,?,?,?,?)',(p['id'],l['id'],s['version'],s['qty'],actor))
    return {'session_id':cur.lastrowid,'captured_version':s['version'],'recorded_qty':s['qty'],'sku':p['sku'],'location':l['warehouse']+'/'+l['code']}

def submit_count(db,data,actor):
    sid=integer(data.get('session_id'),'session_id',1)
    qty=integer(data.get('qty'),'qty')
    session=one(db,'SELECT * FROM count_sessions WHERE id=?',(sid,))
    if not session: raise Failure('INVALID_COUNT_SESSION',404)
    if session['actor']!=actor: raise Failure('FORBIDDEN',403)
    if session['status']!='OPEN': raise Failure('INVALID_STATE_TRANSITION',409)
    s=one(db,'SELECT * FROM stock WHERE product_id=? AND location_id=?',(session['product_id'],session['location_id']))
    # count remains an observation even if inventory moved while counting
    status='STALE' if s['version']!=session['captured_version'] else ('VERIFIED' if qty==s['qty'] else 'DISCREPANCY')
    cur=db.execute('INSERT INTO evidence(session_id,product_id,location_id,observed_qty,captured_version,actor,status) VALUES(?,?,?,?,?,?,?)',(sid,session['product_id'],session['location_id'],qty,session['captured_version'],actor,status))
    db.execute("UPDATE count_sessions SET status='SUBMITTED' WHERE id=?",(sid,))
    return {'evidence_id':cur.lastrowid,'status':status,'evidence_version':session['captured_version'],'current_version':s['version']}

def investigation(db, query):
    if query.get('evidence_id'):
        eid=integer(int(query['evidence_id'][0]) if query['evidence_id'][0].isdigit() else None,'evidence_id',1)
        e=one(db,'SELECT e.*,cs.captured_qty FROM evidence e JOIN count_sessions cs ON cs.id=e.session_id WHERE e.id=?',(eid,))
        if not e: raise Failure('INVALID_EVIDENCE',404)
        p=one(db,'SELECT * FROM products WHERE id=?',(e['product_id'],))
        l=one(db,'SELECT l.*,w.code warehouse FROM locations l JOIN warehouses w ON w.id=l.warehouse_id WHERE l.id=?',(e['location_id'],))
        s=one(db,'SELECT * FROM stock WHERE product_id=? AND location_id=?',(p['id'],l['id']))
    else:
        p,l,s=scope(db,query.get('sku',[None])[0],query.get('location',[None])[0])
        e=one(db,'SELECT e.*,cs.captured_qty FROM evidence e JOIN count_sessions cs ON cs.id=e.session_id WHERE e.product_id=? AND e.location_id=? ORDER BY e.id DESC LIMIT 1',(p['id'],l['id']))
    if not e:
        return {'sku':p['sku'],'name':p['name'],'location':l['warehouse']+'/'+l['code'],'current':{'qty':s['qty'],'version':s['version']},'evidence':None,'last_verified':None,'events':[],'event_total':0,'signals':[{'type':'NO_EVIDENCE','text':'No physical count is recorded for this SKU and location. Requires verification.'}],'resolution':None}
    previous=one(db,"SELECT id,observed_qty,captured_version,submitted_at FROM evidence WHERE product_id=? AND location_id=? AND id<? AND status='VERIFIED' ORDER BY id DESC LIMIT 1",(p['id'],l['id'],e['id']))
    anchor=previous['captured_version'] if previous else e['captured_version']
    where='m.product_id=? AND ((m.source_id=? AND m.source_version>? AND m.source_version<=?) OR (m.dest_id=? AND m.dest_version>? AND m.dest_version<=?))'
    args=(p['id'],l['id'],anchor,s['version'],l['id'],anchor,s['version'])
    total=one(db,'SELECT COUNT(*) n FROM movements m WHERE '+where,args)['n']
    events=rows(db,'SELECT m.ref,m.kind,m.qty,m.created_at,m.source_version,m.dest_version,sw.code || "/" || sl.code source,dw.code || "/" || dl.code destination,u.username actor_name FROM movements m JOIN users u ON u.id=m.actor LEFT JOIN locations sl ON sl.id=m.source_id LEFT JOIN warehouses sw ON sw.id=sl.warehouse_id LEFT JOIN locations dl ON dl.id=m.dest_id LEFT JOIN warehouses dw ON dw.id=dl.warehouse_id WHERE '+where+' ORDER BY m.id DESC LIMIT 50',args)
    resolution=one(db,'SELECT r.id,r.movement_ref,r.note,r.created_at,u.username actor_name FROM resolutions r JOIN users u ON u.id=r.actor WHERE r.evidence_id=?',(e['id'],))
    signals=[]
    if e['captured_version']!=s['version']:
        signals.append({'type':'STALE','text':'Recorded inventory changed after this count. The observation cannot authorize a delivery; recount at the current version.'})
    if e['observed_qty']!=e['captured_qty']:
        signals.append({'type':'VARIANCE','text':'Physical observation differs from the recorded quantity at count start. Cause is not established by this count.'})
    if events:
        signals.append({'type':'RECORDED_EVENTS','text':'Recorded movements exist in this location since the previous verified count'+(' (including events after this count).' if e['captured_version']!=s['version'] else '. No event alone proves the physical variance.')})
        if any(m['kind']=='TRANSFER' for m in events):
            signals.append({'type':'TRANSFER_RECORDED','text':'A transfer touched this bin. Verify the source and destination before attributing a physical variance.'})
        if any(m['kind']=='ADJUST' for m in events):
            signals.append({'type':'ADJUSTMENT_RECORDED','text':'An explicit adjustment changed the ledger. Review its reference and resolution note where available.'})
    elif e['observed_qty']!=e['captured_qty']:
        signals.append({'type':'UNEXPLAINED','text':'No recorded movement in this version window explains the physical variance. Check the bin and transaction records.'})
    if resolution: signals.append({'type':'RESOLVED','text':'An explicit adjustment was logged. A new agreeing count is still required for delivery.'})
    if not signals: signals.append({'type':'AGREES','text':'The recorded and observed quantities agreed at count submission. This does not prove physical truth.'})
    return {'sku':p['sku'],'name':p['name'],'location':l['warehouse']+'/'+l['code'],'current':{'qty':s['qty'],'version':s['version']},'evidence':{'id':e['id'],'expected':e['captured_qty'],'observed':e['observed_qty'],'variance':e['observed_qty']-e['captured_qty'],'captured_version':e['captured_version'],'status_at_submission':e['status'],'submitted_at':e['submitted_at']},'last_verified':previous,'events':events,'event_total':total,'signals':signals,'resolution':resolution}

def resolve(db,data,actor):
    eid=integer(data.get('evidence_id'),'evidence_id',1)
    ref=text(data.get('ref'),'ref',80)
    note=text(data.get('note'),'note',500)
    e=one(db,'SELECT * FROM evidence WHERE id=?',(eid,))
    if not e: raise Failure('INVALID_EVIDENCE',404)
    if one(db,'SELECT id FROM resolutions WHERE evidence_id=?',(eid,)): raise Failure('ALREADY_RESOLVED',409)
    if one(db,'SELECT id FROM movements WHERE ref=?',(ref,)) or one(db,'SELECT ref FROM deliveries WHERE ref=?',(ref,)): raise Failure('DUPLICATE_REFERENCE',409)
    s=one(db,'SELECT * FROM stock WHERE product_id=? AND location_id=?',(e['product_id'],e['location_id']))
    latest=one(db,'SELECT id FROM evidence WHERE product_id=? AND location_id=? ORDER BY id DESC',(e['product_id'],e['location_id']))
    if s['version']!=e['captured_version'] or latest['id']!=eid: raise Failure('STALE_EVIDENCE',409)
    if e['status']!='DISCREPANCY' or e['observed_qty']==s['qty']: raise Failure('NOT_AN_OPEN_DISCREPANCY',409)
    p=one(db,'SELECT * FROM products WHERE id=?',(e['product_id'],))
    l=one(db,'SELECT * FROM locations WHERE id=?',(e['location_id'],))
    version=stock_change(db,p,l,e['observed_qty']-s['qty'])
    db.execute('INSERT INTO movements(ref,kind,product_id,source_id,qty,source_version,actor) VALUES(?,?,?,?,?,?,?)',(ref,'ADJUST',p['id'],l['id'],e['observed_qty'],version,actor))
    db.execute('INSERT INTO resolutions(evidence_id,movement_ref,note,actor) VALUES(?,?,?,?)',(eid,ref,note,actor))
    return {'status':'ADJUSTED','ref':ref,'evidence_id':eid,'previous':s['qty'],'current':e['observed_qty'],'version':version,'required_action':'RECOUNT'}

def decide(db,ref,p,l,s,qty,actor,stage):
    all_e=rows(db,'SELECT * FROM evidence WHERE product_id=? AND location_id=? ORDER BY id DESC',(p['id'],l['id']))
    latest=all_e[0] if all_e else None
    current=[e for e in all_e if e['captured_version']==s['version']]
    if s['qty']<qty: reason='INSUFFICIENT_STOCK'
    elif not latest: reason='MISSING_PHYSICAL_EVIDENCE'
    elif not current: reason='STALE_PHYSICAL_EVIDENCE'
    elif len({e['observed_qty'] for e in current})>1: reason='CONFLICTING_PHYSICAL_EVIDENCE'
    elif current[0]['observed_qty']!=s['qty']: reason='DISCREPANCY'
    else: reason='VERIFIED'
    e=current[0] if current else latest
    status='ALLOWED' if reason=='VERIFIED' else 'BLOCKED'
    db.execute('INSERT INTO decisions(ref,stage,status,reason,evidence_version,current_version,evidence_id,stock_qty,actor) VALUES(?,?,?,?,?,?,?,?,?)',(ref,stage,status,reason,e['captured_version'] if e else None,s['version'],e['id'] if e else None,s['qty'],actor))
    return {'status':status,'reason':reason,'sku':p['sku'],'location':l['warehouse']+'/'+l['code'],'evidence_version':e['captured_version'] if e else None,'current_version':s['version'],'recorded':s['qty'],'requested':qty,'required_action':'RECOUNT' if reason!='INSUFFICIENT_STOCK' and status=='BLOCKED' else ('RECEIVE_STOCK' if status=='BLOCKED' else None),'ref':ref,'stage':stage}

def delivery(db,data,actor,commit=False):
    ref=text(data.get('ref'),'ref',80)
    p,l,s=scope(db,data.get('sku'),data.get('location'))
    qty=integer(data.get('qty'),'qty',1)
    contact=data.get('contact')
    if contact == '': contact=None
    if contact is not None: contact=text(contact,'contact')
    order=one(db,'SELECT * FROM deliveries WHERE ref=?',(ref,))
    if not order:
        if one(db,'SELECT id FROM movements WHERE ref=?',(ref,)): raise Failure('DUPLICATE_REFERENCE',409)
        db.execute('INSERT INTO deliveries(ref,product_id,location_id,qty,contact,state,actor) VALUES(?,?,?,?,?,?,?)',(ref,p['id'],l['id'],qty,contact,'PENDING',actor))
    elif (order['product_id'],order['location_id'],order['qty'],order['contact'])!=(p['id'],l['id'],qty,contact):
        raise Failure('DUPLICATE_REFERENCE',409)
    elif order['state']=='DONE':
        return {'status':'COMPLETED','reason':'ALREADY_COMPLETED','ref':ref,'movement_ref':ref}
    elif order['state']!='PENDING': raise Failure('INVALID_STATE_TRANSITION',409)
    result=decide(db,ref,p,l,s,qty,actor,'COMMIT' if commit else 'PREFLIGHT')
    if commit and result['status']=='ALLOWED':
        version=stock_change(db,p,l,-qty)
        db.execute('INSERT INTO movements(ref,kind,product_id,source_id,qty,source_version,actor,contact) VALUES(?,?,?,?,?,?,?,?)',(ref,'DELIVER',p['id'],l['id'],qty,version,actor,contact))
        db.execute("UPDATE deliveries SET state='DONE' WHERE ref=?",(ref,))
        result.update(status='COMPLETED',remaining=s['qty']-qty,movement_ref=ref)
    return result

def list_data(db,name,query):
    if name=='inventory':
        sql='SELECT p.sku,p.name,p.uom,p.reorder_point,c.name category,w.code warehouse,l.code location,s.qty,s.version FROM stock s JOIN products p ON p.id=s.product_id JOIN locations l ON l.id=s.location_id JOIN warehouses w ON w.id=l.warehouse_id LEFT JOIN categories c ON c.id=p.category_id WHERE 1=1'
        args=[]
        for k,col in [('search','p.sku'),('warehouse','w.code'),('location','l.code'),('category','c.name')]:
            if query.get(k): sql+=' AND '+col+(' LIKE ?' if k=='search' else '=?');args.append('%'+query[k][0]+'%' if k=='search' else query[k][0])
        return rows(db,sql+' ORDER BY p.sku,w.code,l.code',args)
    if name=='movements': return rows(db,'SELECT m.*,p.sku,sw.code || "/" || sl.code source,dw.code || "/" || dl.code destination,u.username actor_name FROM movements m JOIN products p ON p.id=m.product_id JOIN users u ON u.id=m.actor LEFT JOIN locations sl ON sl.id=m.source_id LEFT JOIN warehouses sw ON sw.id=sl.warehouse_id LEFT JOIN locations dl ON dl.id=m.dest_id LEFT JOIN warehouses dw ON dw.id=dl.warehouse_id ORDER BY m.id DESC LIMIT 200')
    if name=='decisions': return rows(db,'SELECT d.*,p.sku,w.code || "/" || l.code location FROM decisions d JOIN deliveries o ON o.ref=d.ref JOIN products p ON p.id=o.product_id JOIN locations l ON l.id=o.location_id JOIN warehouses w ON w.id=l.warehouse_id ORDER BY d.id DESC LIMIT 200')
    if name=='evidence': return rows(db,'SELECT e.*,p.sku,w.code || "/" || l.code location,u.username actor_name FROM evidence e JOIN products p ON p.id=e.product_id JOIN locations l ON l.id=e.location_id JOIN warehouses w ON w.id=l.warehouse_id JOIN users u ON u.id=e.actor ORDER BY e.id DESC LIMIT 200')
    if name=='deliveries': return rows(db,'SELECT o.*,p.sku,w.code || "/" || l.code location FROM deliveries o JOIN products p ON p.id=o.product_id JOIN locations l ON l.id=o.location_id JOIN warehouses w ON w.id=l.warehouse_id ORDER BY o.created_at DESC')
    if name=='investigations': return investigation(db,query)
    if name=='resolutions': return rows(db,'SELECT r.*,e.observed_qty,p.sku,w.code || "/" || l.code location,u.username actor_name FROM resolutions r JOIN evidence e ON e.id=r.evidence_id JOIN products p ON p.id=e.product_id JOIN locations l ON l.id=e.location_id JOIN warehouses w ON w.id=l.warehouse_id JOIN users u ON u.id=r.actor ORDER BY r.id DESC LIMIT 200')
    if name=='dashboard':
        return {'products':one(db,'SELECT COUNT(*) n FROM products')['n'],'units':one(db,'SELECT COALESCE(SUM(qty),0) n FROM stock')['n'],'low_stock':one(db,'SELECT COUNT(*) n FROM stock s JOIN products p ON p.id=s.product_id WHERE s.qty<=p.reorder_point')['n'],'pending_deliveries':one(db,"SELECT COUNT(*) n FROM deliveries WHERE state='PENDING'")['n'],'held_decisions':one(db,"SELECT COUNT(*) n FROM decisions WHERE status='BLOCKED'")['n']}
    if name in ('products','warehouses','locations','categories'):
        return rows(db,{'products':'SELECT p.*,c.name category FROM products p LEFT JOIN categories c ON c.id=p.category_id ORDER BY p.sku','warehouses':'SELECT * FROM warehouses ORDER BY code','locations':'SELECT l.*,w.code warehouse FROM locations l JOIN warehouses w ON w.id=l.warehouse_id ORDER BY w.code,l.code','categories':'SELECT * FROM categories ORDER BY name'}[name])
    raise Failure('INVALID_RESOURCE',404)

class Handler(BaseHTTPRequestHandler):
    def respond(self,status,obj):
        raw=json.dumps(obj).encode()
        self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(raw))); self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)
    def handle_api(self):
        parsed=urlparse(self.path)
        if not parsed.path.startswith('/api/'):
            if self.command!='GET' or parsed.path not in ('/','/index.html'): raise Failure('NOT_FOUND',404)
            raw=Path(__file__).with_name('index.html').read_bytes()
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);return
        name=parsed.path[5:]
        if self.command=='POST':
            try: size=int(self.headers.get('Content-Length','0'))
            except ValueError: raise Failure('MALFORMED_INPUT')
            if size<1 or size>16384: raise Failure('MALFORMED_INPUT')
            try: data=json.loads(self.rfile.read(size))
            except (ValueError,UnicodeDecodeError): raise Failure('MALFORMED_INPUT')
            if not isinstance(data,dict): raise Failure('MALFORMED_INPUT')
        with transaction() as db:
            if self.command=='POST' and name in ('signup','login'):
                result=login(db,data,name=='signup')
            else:
                token=self.headers.get('Authorization','').removeprefix('Bearer ')
                actor=auth(db,token)
                if self.command=='GET':
                    if name=='counts/open':
                        result=one(db,"SELECT cs.id session_id,cs.captured_version,cs.captured_qty recorded_qty,p.sku,w.code || '/' || l.code location FROM count_sessions cs JOIN products p ON p.id=cs.product_id JOIN locations l ON l.id=cs.location_id JOIN warehouses w ON w.id=l.warehouse_id WHERE cs.actor=? AND cs.status='OPEN' ORDER BY cs.id DESC LIMIT 1",(actor,))
                    else:result=list_data(db,name,parse_qs(parsed.query))
                elif name=='logout': db.execute('DELETE FROM sessions WHERE token=?',(token,));result={'status':'LOGGED_OUT'}
                elif name=='products/update':result=update_product(db,data)
                elif name in ('products','warehouses','locations','categories'):result=create(db,name,data)
                elif name=='movements':result=movement(db,data,actor)
                elif name=='investigations/resolve':result=resolve(db,data,actor)
                elif name=='counts/start':result=start_count(db,data,actor)
                elif name=='counts/submit':result=submit_count(db,data,actor)
                elif name in ('deliveries/preflight','deliveries/commit'):result=delivery(db,data,actor,name.endswith('commit'))
                else:raise Failure('NOT_FOUND',404)
        self.respond(200,result)
    def do_GET(self): self.run()
    def do_POST(self): self.run()
    def run(self):
        try: self.handle_api()
        except Failure as e: self.respond(e.status,{'error':e.code})
        except sqlite3.IntegrityError as e: self.respond(409,{'error':'CONSTRAINT_VIOLATION'})
        except (TypeError,ValueError) as e: self.respond(400,{'error':'MALFORMED_INPUT'})
    def log_message(self,fmt,*args): print('%s %s'%(self.address_string(),fmt%args))

if __name__=='__main__':
    init(); host=os.environ.get('VEYRA_HOST','127.0.0.1');port=int(os.environ.get('VEYRA_PORT','8000'))
    print(f'Veyra at http://{host}:{port}',flush=True)
    ThreadingHTTPServer((host,port),Handler).serve_forever()
