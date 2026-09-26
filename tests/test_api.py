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
            for table in ('decisions','resolutions','movements','deliveries','evidence','count_sessions','stock','sessions','locations','warehouses','products','categories','users'):
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
        self.assertEqual(sum(s['qty'] for s in self.api('inventory')[1]),10) # transfer conserves total
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
    def test_investigation_resolution_and_recount(self):
        self.count(10)
        _,ev=self.api('counts/start',{'sku':'S','location':'WH/A'})
        _,dis=self.api('counts/submit',{'session_id':ev['session_id'],'qty':9})
        eid=dis['evidence_id']
        status,case=self.api('investigations?evidence_id='+str(eid))
        self.assertEqual((status,case['evidence']['expected'],case['evidence']['observed'],case['evidence']['variance']),(200,10,9,-1))
        self.assertEqual(case['last_verified']['observed_qty'],10)
        self.assertEqual(case['event_total'],0)
        self.assertIn('UNEXPLAINED',[s['type'] for s in case['signals']])
        self.assertEqual(self.api('deliveries/commit',self.order())[1]['reason'],'CONFLICTING_PHYSICAL_EVIDENCE')
        resolution={'evidence_id':eid,'ref':'ADJ1','note':'Bin recounted by operator; one missing'}
        self.assertEqual(self.api('investigations/resolve',resolution)[1]['required_action'],'RECOUNT')
        self.assertEqual(self.api('investigations/resolve',resolution)[1]['error'],'ALREADY_RESOLVED')
        self.assertEqual(self.api('movements',{'ref':'ADJ1','kind':'RECEIVE','sku':'S','location':'WH/A','qty':1})[1]['error'],'DUPLICATE_REFERENCE')
        _,case=self.api('investigations?evidence_id='+str(eid))
        self.assertEqual(case['current'],{'qty':9,'version':1})
        self.assertEqual(case['resolution']['movement_ref'],'ADJ1')
        self.assertEqual(case['event_total'],1)
        self.assertEqual(case['events'][0]['ref'],'ADJ1')
        self.assertEqual(self.api('deliveries/commit',self.order())[1]['reason'],'STALE_PHYSICAL_EVIDENCE')
        self.count(9)
        self.assertEqual(self.api('deliveries/commit',self.order())[1]['status'],'COMPLETED')
        self.assertEqual(self.api('resolutions')[1][0]['note'],resolution['note'])
        self.assertEqual(self.api('inventory')[1][0]['qty'],0)
    def test_investigation_stale_tampering_and_authorization(self):
        self.assertEqual(self.call('investigations?sku=S&location=WH/A')[0],401)
        self.assertIsNone(self.api('investigations?sku=S&location=WH/A')[1]['evidence'])
        _,start=self.api('counts/start',{'sku':'S','location':'WH/A'})
        _,ev=self.api('counts/submit',{'session_id':start['session_id'],'qty':9})
        eid=ev['evidence_id']
        self.assertEqual(self.call('investigations/resolve',{'evidence_id':eid,'ref':'X','note':'checked'})[0],401)
        self.assertEqual(self.api('investigations?evidence_id=999999')[0],404)
        self.assertEqual(self.api('investigations?evidence_id=oops')[0],400)
        self.assertEqual(self.api('investigations/resolve',{'evidence_id':eid,'ref':'X','note':''})[1]['error'],'INVALID_NOTE')
        self.api('movements',{'kind':'RECEIVE','ref':'R1','sku':'S','location':'WH/A','qty':2})
        _,case=self.api('investigations?evidence_id='+str(eid))
        self.assertEqual(case['event_total'],1)
        self.assertEqual(case['events'][0]['dest_version'],1)
        self.assertIn('STALE',[s['type'] for s in case['signals']])
        self.assertEqual(self.api('investigations/resolve',{'evidence_id':eid,'ref':'X','note':'checked'})[1]['error'],'STALE_EVIDENCE')
        self.assertEqual(self.api('inventory')[1][0]['qty'],12)
        self.assertEqual(len(self.api('resolutions')[1]),0)
    def test_seeded_demo_story_from_persisted_versions(self):
        with veyra.transaction() as db:
            db.execute('UPDATE stock SET qty=768,version=0 WHERE product_id=1 AND location_id=1')
        self.assertEqual(self.count(761)['status'],'DISCREPANCY')
        _,case=self.api('investigations?sku=S&location=WH/A')
        self.assertEqual((case['evidence']['expected'],case['evidence']['observed'],case['evidence']['variance']),(768,761,-7))
        eid=case['evidence']['id']
        self.assertEqual(self.api('investigations/resolve',{'evidence_id':eid,'ref':'A1','note':'Physical bin verified, investigate missing 7'})[1]['version'],1)
        self.assertEqual(self.count(761)['status'],'VERIFIED')
        self.assertEqual(self.api('movements',{'ref':'R1','kind':'RECEIVE','sku':'S','location':'WH/A','qty':2})[0],200)
        o=self.order('D1',qty=9)
        self.assertEqual(self.api('deliveries/commit',o)[1]['reason'],'STALE_PHYSICAL_EVIDENCE')
        self.assertEqual(self.count(763)['status'],'VERIFIED')
        self.assertEqual(self.api('deliveries/commit',o)[1]['remaining'],754)
        self.assertEqual(self.api('inventory')[1][0]['version'],3)
        self.assertEqual([m['ref'] for m in self.api('movements')[1]],['D1','R1','A1'])
    def test_open_count_survives_new_connection_and_is_actor_scoped(self):
        _,started=self.api('counts/start',{'sku':'S','location':'WH/A'})
        self.assertEqual(self.api('counts/open')[1]['session_id'],started['session_id'])
        _,other=self.call('signup',{'username':'second','password':'password1234'})
        self.assertIsNone(self.call('counts/open',token=other['token'])[1])
        self.assertEqual(self.call('counts/submit',{'session_id':started['session_id'],'qty':9},other['token'])[0],403)
        self.assertEqual(self.api('counts/submit',{'session_id':started['session_id'],'qty':9})[0],200)
        self.assertIsNone(self.api('counts/open')[1])
    def test_concurrent_resolution_only_one_adjustment(self):
        _,start=self.api('counts/start',{'sku':'S','location':'WH/A'})
        _,ev=self.api('counts/submit',{'session_id':start['session_id'],'qty':9})
        data={'evidence_id':ev['evidence_id'],'ref':'A1','note':'verified manually'}
        barrier=threading.Barrier(3);out=[]
        def run():barrier.wait();out.append(self.api('investigations/resolve',data))
        a=threading.Thread(target=run);b=threading.Thread(target=run);a.start();b.start();barrier.wait();a.join();b.join()
        self.assertEqual(sorted(status for status,_ in out),[200,409])
        self.assertEqual(len(self.api('resolutions')[1]),1)
        self.assertEqual(len(self.api('movements')[1]),1)
        self.assertEqual(self.api('inventory')[1][0]['qty'],9)
    def test_concurrent_commits_one_movement(self):
        self.count();o=self.order();barrier=threading.Barrier(3);out=[]
        def run():barrier.wait();out.append(self.api('deliveries/commit',o))
        a=threading.Thread(target=run);b=threading.Thread(target=run);a.start();b.start();barrier.wait();a.join();b.join()
        self.assertEqual(sorted(x[1]['status'] for x in out),['COMPLETED','COMPLETED'])
        self.assertEqual(len(self.api('movements')[1]),1)
        self.assertEqual(self.api('inventory')[1][0]['qty'],1)

if __name__=='__main__':unittest.main()
