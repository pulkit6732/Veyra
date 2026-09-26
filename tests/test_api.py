import json
import os
import sqlite3
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import veyra

class API(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        veyra.DB=os.path.join(cls.tmp.name,'test.sqlite3')
        veyra.init()
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),veyra.Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.base=f'http://127.0.0.1:{cls.server.server_port}/api/'
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.tmp.cleanup()
    def call(self,path,payload=None,token=None,raw=None):
        body=raw if raw is not None else (json.dumps(payload).encode() if payload is not None else None)
        req=Request(self.base+path,data=body,headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+token} if token else {})})
        try:
            with urlopen(req) as r:return r.status,json.load(r)
        except HTTPError as e:
            try:return e.code,json.load(e)
            finally:e.close()
    def setUp(self):
        with veyra.transaction() as db:
            for table in ('decisions','movements','deliveries','evidence','count_sessions','stock','sessions','locations','warehouses','products','categories','users'):
                db.execute('DELETE FROM '+table)
        _,u=self.call('signup',{'username':'worker','password':'longpassword123'})
        self.token=u['token'];self.setup_base()
    def api(self,path,data=None):return self.call(path,data,self.token)
    def setup_base(self):
        for path,data in [('categories',{'name':'Parts'}),('products',{'sku':'S','name':'Steel','category':'Parts','reorder_point':4}),('warehouses',{'code':'WH','name':'Main'}),('warehouses',{'code':'OTHER','name':'Other'}),('locations',{'code':'A','name':'Bin A','warehouse':'WH'}),('locations',{'code':'B','name':'Bin B','warehouse':'OTHER'})]:
            self.assertEqual(self.api(path,data)[0],200)
        # explicit demo initialization before any movement, only in isolated test database
        with veyra.transaction() as db:
            db.execute('INSERT INTO stock(product_id,location_id,qty,version) VALUES(1,1,10,0)')
    def count(self,qty=10,location='WH/A'):
        _,start=self.api('counts/start',{'sku':'S','location':location})
        return self.api('counts/submit',{'session_id':start['session_id'],'qty':qty})[1]
    def order(self,ref='D1',location='WH/A',qty=9):return {'ref':ref,'sku':'S','location':location,'qty':qty}
    def test_primary_flow_and_idempotency(self):
        self.assertEqual(self.count()['evidence_version'],0)
        self.assertEqual(self.api('movements',{'ref':'R1','kind':'RECEIVE','sku':'S','location':'WH/A','qty':2})[1]['dest_version'],1)
        o=self.order()
        status,pre=self.api('deliveries/preflight',o);self.assertEqual(pre['reason'],'STALE_PHYSICAL_EVIDENCE')
        status,held=self.api('deliveries/commit',o);self.assertEqual((status,held['status'],held['recorded'],held['evidence_version'],held['current_version']),(200,'BLOCKED',12,0,1))
        self.assertEqual(held['required_action'],'RECOUNT')
        self.assertEqual(self.count(12)['status'],'VERIFIED')
        _,done=self.api('deliveries/commit',o);self.assertEqual((done['status'],done['remaining']),( 'COMPLETED',3))
        self.assertEqual(self.api('deliveries/commit',o)[1]['reason'],'ALREADY_COMPLETED')
        movements=self.api('movements')[1];self.assertEqual(len([m for m in movements if m['kind']=='DELIVER']),1)
        self.assertEqual(self.api('inventory')[1][0]['qty'],3)
        self.assertEqual([d['reason'] for d in self.api('decisions')[1]],['VERIFIED','STALE_PHYSICAL_EVIDENCE','STALE_PHYSICAL_EVIDENCE'])
    def test_missing_insufficient_and_invalid(self):
        self.assertEqual(self.api('deliveries/commit',self.order())[1]['reason'],'MISSING_PHYSICAL_EVIDENCE')
        self.assertEqual(self.api('deliveries/commit',self.order('D2',qty=11))[1]['reason'],'INSUFFICIENT_STOCK')
        self.assertEqual(self.api('deliveries/commit',self.order('D3',qty=0))[1]['error'],'INVALID_QTY')
        self.assertEqual(self.api('counts/start',{'sku':'BAD','location':'WH/A'})[0],404)
        self.assertEqual(self.api('counts/start',{'sku':'S','location':'BAD'})[0],404)
        self.assertEqual(self.call('inventory')[0],401)
        self.assertEqual(self.call('deliveries/commit',raw=b'{oops',token=self.token)[1]['error'],'MALFORMED_INPUT')
    def test_stale_during_count_and_between_preflight_commit(self):
        _,start=self.api('counts/start',{'sku':'S','location':'WH/A'})
        self.api('movements',{'ref':'R2','kind':'RECEIVE','sku':'S','location':'WH/A','qty':2})
        self.assertEqual(self.api('counts/submit',{'session_id':start['session_id'],'qty':12})[1]['status'],'STALE')
        self.assertEqual(self.api('counts/submit',{'session_id':start['session_id'],'qty':12})[1]['error'],'INVALID_STATE_TRANSITION')
        self.count(12)
        o=self.order();self.assertEqual(self.api('deliveries/preflight',o)[1]['status'],'ALLOWED')
        self.api('movements',{'ref':'R3','kind':'RECEIVE','sku':'S','location':'WH/A','qty':1})
        self.assertEqual(self.api('deliveries/commit',o)[1]['reason'],'STALE_PHYSICAL_EVIDENCE')
    def test_conflict_discrepancy_and_explicit_adjustment(self):
        self.count(10);self.count(9)
        self.assertEqual(self.api('deliveries/commit',self.order())[1]['reason'],'CONFLICTING_PHYSICAL_EVIDENCE')
        self.assertEqual(self.api('inventory')[1][0]['qty'],10)
        self.assertEqual(self.api('movements',{'kind':'ADJUST','ref':'A1','sku':'S','location':'WH/A','qty':9})[0],200)
        self.assertEqual(self.api('inventory')[1][0]['qty'],9)
        self.assertEqual(self.api('deliveries/commit',self.order())[1]['reason'],'STALE_PHYSICAL_EVIDENCE')
        self.count(9);self.assertEqual(self.api('deliveries/commit',self.order())[1]['status'],'COMPLETED')
    def test_transfer_scoped_and_duplicate_reference(self):
        self.count()
        transfer={'kind':'TRANSFER','ref':'T1','sku':'S','location':'WH/A','destination':'OTHER/B','qty':3}
        self.assertEqual(self.api('movements',transfer)[0],200)
        self.assertEqual(self.api('movements',transfer)[1]['error'],'DUPLICATE_REFERENCE')
        self.assertEqual(next(s['qty'] for s in self.api('inventory')[1] if s['location']=='A'),7)
        self.assertEqual(self.api('deliveries/commit',self.order('D1',qty=6))[1]['reason'],'STALE_PHYSICAL_EVIDENCE')
        self.assertEqual(self.api('deliveries/commit',self.order('D2',location='OTHER/B',qty=2))[1]['reason'],'MISSING_PHYSICAL_EVIDENCE')
        self.assertEqual(self.api('deliveries/commit',self.order('T1'))[1]['error'],'DUPLICATE_REFERENCE')
    def test_input_auth_update_and_boundaries(self):
        self.assertEqual(self.api('products/update',{'sku':'S','name':'Steel bracket'})[1]['status'],'UPDATED')
        self.assertEqual(self.api('products')[1][0]['name'],'Steel bracket')
        self.assertEqual(self.api('products/update',{'sku':'S','reorder_point':-1})[1]['error'],'INVALID_REORDER_POINT')
        self.assertEqual(self.api('movements',{'kind':'RECEIVE','ref':'bad','sku':'S','location':'WH/A','qty':'2'})[1]['error'],'INVALID_QTY')
        self.assertEqual(self.api('deliveries/commit',dict(self.order(),contact={'bad':1}))[1]['error'],'INVALID_CONTACT')
        _,second=self.call('signup',{'username':'other','password':'anotherlongpassword'})
        _,s=self.api('counts/start',{'sku':'S','location':'WH/A'})
        self.assertEqual(self.call('counts/submit',{'session_id':s['session_id'],'qty':10},second['token'])[1]['error'],'FORBIDDEN')
        self.assertEqual(self.call('movements',{'kind':'RECEIVE','ref':'N1','sku':'S','location':'WH/A','qty':2})[0],401)
        self.assertEqual(self.api('inventory')[1][0]['qty'],10)
    def test_concurrent_commits_one_movement(self):
        self.count();o=self.order();barrier=threading.Barrier(3);out=[]
        def run():barrier.wait();out.append(self.api('deliveries/commit',o))
        a=threading.Thread(target=run);b=threading.Thread(target=run);a.start();b.start();barrier.wait();a.join();b.join()
        self.assertEqual(sorted(x[1]['status'] for x in out),['COMPLETED','COMPLETED'])
        self.assertEqual(len(self.api('movements')[1]),1)
        self.assertEqual(self.api('inventory')[1][0]['qty'],1)

if __name__=='__main__':unittest.main()
