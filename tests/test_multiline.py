import threading
import unittest
from test_api import API
import veyra


class Multiline(unittest.TestCase):
    setUpClass=classmethod(API.setUpClass.__func__)
    tearDownClass=classmethod(API.tearDownClass.__func__)
    call=API.call
    api=API.api
    setup_base=API.setup_base
    def setUp(self):
        API.setUp(self)
        self.api('products', {'sku':'B','name':'Brass'})
        with veyra.transaction() as db:
            db.execute('INSERT INTO stock(product_id,location_id,qty,version) VALUES(2,1,5,0)')

    def step(self,ref,action,qty=None,line_id=None):
        body={'ref':ref,'action':action}
        if qty is not None:body['qty']=qty
        if line_id is not None:body['line_id']=line_id
        return self.api('deliveries/step',body)

    def doc(self, ref='M', second=3):
        return {'ref':ref,'destination':'Site','lines':[{'sku':'S','location':'WH/A','qty':4},{'sku':'B','location':'WH/A','qty':second}]}

    def ready(self, doc):
        self.assertEqual(self.api('deliveries/preflight',doc)[0],200)
        ref=doc['ref']
        lines=self.api('deliveries')[1][0]['lines']
        for a in ('READY','START_PICKING'): self.assertEqual(self.step(ref,a)[0],200)
        self.assertEqual(self.step(ref,'COMPLETE_PICKING')[1]['error'],'PICKING_INCOMPLETE')
        for l in lines: self.assertEqual(self.step(ref,'PICK',l['qty'],l['id'])[0],200)
        self.step(ref,'COMPLETE_PICKING');self.step(ref,'START_PACKING')
        self.assertEqual(self.step(ref,'COMPLETE_PACKING')[1]['error'],'PACKING_INCOMPLETE')
        for l in lines: self.assertEqual(self.step(ref,'PACK',l['qty'],l['id'])[0],200)
        self.step(ref,'COMPLETE_PACKING')
        return lines

    def counted(self,sku,qty):
        _,s=self.api('counts/start',{'sku':sku,'location':'WH/A'})
        self.assertEqual(self.api('counts/submit',{'session_id':s['session_id'],'qty':qty})[1]['status'],'VERIFIED')

    def inventory(self):return {x['sku']:(x['qty'],x['version']) for x in self.api('inventory')[1]}
    def delivers(self):return [m for m in self.api('movements')[1] if m['kind']=='DELIVER']

    def test_block_final_line_no_partial_then_recount_only_affected(self):
        self.counted('S',10);self.counted('B',5)
        d=self.doc();self.ready(d)
        self.api('movements',{'ref':'T','kind':'ADJUST','sku':'B','location':'WH/A','qty':2})
        before=self.inventory()
        _,r=self.api('deliveries/commit',{'ref':'M'})
        self.assertEqual((r['status'],[l['reason'] for l in r['lines']]),('BLOCKED',['VERIFIED','INSUFFICIENT_STOCK']))
        self.assertEqual(self.inventory(),before);self.assertEqual(self.delivers(),[])
        self.assertEqual(self.api('deliveries')[1][0]['state'],'PACKED')
        self.assertEqual([e for e in self.api('delivery-events')[1] if e['action']=='COMMIT'],[])
        self.api('movements',{'ref':'R','kind':'RECEIVE','sku':'B','location':'WH/A','qty':3})
        _,held=self.api('deliveries/commit',{'ref':'M'})
        self.assertEqual([x['reason'] for x in held['lines']],['VERIFIED','STALE_PHYSICAL_EVIDENCE'])
        self.counted('B',5)
        self.assertEqual(self.api('deliveries/commit',{'ref':'M'})[1]['status'],'COMPLETED')
        self.assertEqual(self.inventory(),{'S':(6,1),'B':(2,3)})
        self.assertEqual(len(self.delivers()),2)
        self.assertEqual({m['line_id'] for m in self.delivers()},{l['id'] for l in self.api('deliveries')[1][0]['lines']})
        self.assertEqual(self.api('investigations?sku=S&location=WH/A')[1]['events'][0]['delivery_ref'],'M')
        self.assertEqual(self.api('deliveries/commit',{'ref':'M'})[1]['reason'],'ALREADY_COMPLETED')
        self.assertEqual(len(self.delivers()),2)

    def test_atomic_when_late_insert_fails(self):
        self.counted('S',10);self.counted('B',5);self.ready(self.doc())
        line=self.api('deliveries')[1][0]['lines'][1]
        # Fail on the second movement, after the first line's update/event/decision.
        with veyra.transaction() as db:
            db.execute("CREATE TRIGGER fail_second BEFORE INSERT ON movements WHEN NEW.ref='M#%s' BEGIN SELECT RAISE(ABORT,'injected'); END" % line['id'])
        try:
            before=self.inventory()
            self.assertEqual(self.api('deliveries/commit',{'ref':'M'})[0],409)
            self.assertEqual(self.inventory(),before)
            self.assertEqual(self.delivers(),[])
            self.assertEqual(self.api('deliveries')[1][0]['state'],'PACKED')
            self.assertEqual([e for e in self.api('delivery-events')[1] if e['action']=='COMMIT'],[])
            self.assertEqual([d for d in self.api('decisions')[1] if d['stage']=='COMMIT'],[])
        finally:
            with veyra.transaction() as db:db.execute('DROP TRIGGER fail_second')

    def test_generated_movement_refs_cannot_be_taken(self):
        self.counted('S',10);self.counted('B',5)
        self.api('deliveries/preflight',self.doc())
        second=self.api('deliveries')[1][0]['lines'][1]
        reserved='M#'+str(second['id'])
        self.assertEqual(self.api('movements',{'ref':reserved,'kind':'RECEIVE','sku':'S','location':'WH/A','qty':1})[1]['error'],'DUPLICATE_REFERENCE')
        self.assertEqual(self.api('deliveries/preflight',self.doc(reserved))[1]['error'],'DUPLICATE_REFERENCE')
        self.ready(self.doc())
        self.assertEqual(self.api('deliveries/commit',{'ref':'M'})[1]['status'],'COMPLETED')
        self.assertEqual(len(self.delivers()),2)
        self.assertEqual(self.api('inventory')[1][0]['version'],1) # B row sorted before S

    def test_preexisting_generated_ref_rejects_draft_not_final_commit(self):
        # Next line ID is known only to the database; deliberately occupy that name before draft creation.
        with veyra.transaction() as db:
            next_id=db.execute('SELECT COALESCE(MAX(id),0)+2 FROM delivery_lines').fetchone()[0]
        self.api('movements',{'ref':'M#'+str(next_id),'kind':'RECEIVE','sku':'S','location':'OTHER/B','qty':1})
        self.assertEqual(self.api('deliveries/preflight',self.doc())[1]['error'],'DUPLICATE_REFERENCE')
        self.assertEqual(self.api('deliveries')[1],[])
        self.assertEqual(self.api('deliveries/preflight',self.doc('OTHER'))[0],200)

    def test_concurrent_commit_and_auth(self):
        self.counted('S',10);self.counted('B',5);self.ready(self.doc())
        self.assertEqual(self.call('deliveries/commit',{'ref':'M'})[0],401)
        self.assertEqual(self.call('deliveries/step',{'ref':'M','action':'PACK','qty':1})[0],401)
        barrier=threading.Barrier(3);out=[]
        def work():barrier.wait();out.append(self.api('deliveries/commit',{'ref':'M'}))
        threads=[threading.Thread(target=work) for _ in range(2)]
        for t in threads:t.start()
        barrier.wait()
        for t in threads:t.join()
        self.assertEqual(sorted(x[1]['reason'] for x in out),['ALREADY_COMPLETED','VERIFIED'])
        self.assertEqual(self.inventory(),{'S':(6,1),'B':(2,1)})
        self.assertEqual(len(self.delivers()),2)

    def test_racing_inventory_change_never_partially_commits(self):
        self.counted('S',10);self.counted('B',5);self.ready(self.doc())
        barrier=threading.Barrier(3);out=[]
        def deliver():barrier.wait();out.append(self.api('deliveries/commit',{'ref':'M'}))
        def receive():barrier.wait();out.append(self.api('movements',{'ref':'R','kind':'RECEIVE','sku':'B','location':'WH/A','qty':1}))
        threads=[threading.Thread(target=f) for f in (deliver,receive)]
        for t in threads:t.start()
        barrier.wait()
        for t in threads:t.join()
        self.assertEqual([s for s,_ in out],[200,200])
        deliveries=self.delivers()
        self.assertIn(len(deliveries),(0,2))
        if not deliveries:
            self.assertEqual(self.inventory(),{'S':(10,0),'B':(6,1)})
            self.assertEqual(self.api('deliveries')[1][0]['state'],'PACKED')
        else:
            self.assertEqual(self.inventory(),{'S':(6,1),'B':(3,2)})
            self.assertEqual(self.api('deliveries')[1][0]['state'],'DONE')

    def test_concurrent_counts_conflict_and_block_without_stock_change(self):
        self.api('deliveries/preflight',self.doc())
        barrier=threading.Barrier(3);out=[]
        def count(qty):
            barrier.wait()
            status,start=self.api('counts/start',{'sku':'S','location':'WH/A'})
            if status==200:out.append(self.api('counts/submit',{'session_id':start['session_id'],'qty':qty}))
        threads=[threading.Thread(target=count,args=(qty,)) for qty in (9,10)]
        for t in threads:t.start()
        barrier.wait()
        for t in threads:t.join()
        self.assertEqual([x[0] for x in out],[200,200])
        self.assertEqual(self.api('deliveries/preflight',{'ref':'M'})[1]['lines'][0]['reason'],'CONFLICTING_PHYSICAL_EVIDENCE')
        self.assertEqual(self.api('deliveries')[1][0]['lines'][0]['evidence'],'CONFLICT')
        case=self.api('investigations?sku=S&location=WH/A')[1]
        self.assertIn('CONFLICTING_COUNTS',[s['type'] for s in case['signals']])
        self.assertIn('= 9',next(s['text'] for s in case['signals'] if s['type']=='CONFLICTING_COUNTS'))
        self.assertEqual(self.inventory(),{'S':(10,0),'B':(5,0)})

    def test_conflicting_counts_do_not_appear_current_in_delivery(self):
        self.counted('S',10)
        _,started=self.api('counts/start',{'sku':'S','location':'WH/A'})
        self.api('counts/submit',{'session_id':started['session_id'],'qty':9})
        self.api('deliveries/preflight',self.doc())
        doc=self.api('deliveries')[1][0]
        self.assertEqual(doc['lines'][0]['evidence'],'CONFLICT')
        self.assertEqual(self.api('deliveries/preflight',{'ref':'M'})[1]['lines'][0]['reason'],'CONFLICTING_PHYSICAL_EVIDENCE')

    def test_cross_document_line_and_actor_permissions(self):
        self.api('deliveries/preflight',self.doc())
        self.api('deliveries/preflight',self.doc('N'))
        m=self.api('deliveries')[1]
        line_n=next(x for x in m if x['ref']=='N')['lines'][1]['id']
        self.step('M','READY');self.step('M','START_PICKING')
        self.assertEqual(self.step('M','PICK',1,line_n),(404,{'error':'INVALID_DELIVERY_LINE'}))
        self.assertEqual(next(x for x in self.api('deliveries')[1] if x['ref']=='M')['lines'][1]['picked_qty'],0)
        _,other=self.call('signup',{'username':'other','password':'anotherlongpassword'})
        # Any signed-in account can operate another account's delivery: no assigned roles/ownership yet.
        self.assertEqual(self.call('deliveries/step',{'ref':'M','action':'PICK','line_id':next(x for x in m if x['ref']=='M')['lines'][0]['id'],'qty':1},other['token'])[0],200)
        self.assertEqual(self.call('deliveries/commit',{'ref':'M'})[0],401)

    def test_late_stale_count_does_not_hide_current_delivery_hint(self):
        _,old=self.api('counts/start',{'sku':'S','location':'WH/A'})
        self.api('movements',{'ref':'R','kind':'RECEIVE','sku':'S','location':'WH/A','qty':1})
        self.counted('S',11)
        self.api('counts/submit',{'session_id':old['session_id'],'qty':10})
        self.api('deliveries/preflight',self.doc())
        self.assertEqual(self.api('deliveries')[1][0]['lines'][0]['evidence'],'CURRENT')
        self.assertEqual(self.api('deliveries/preflight',{'ref':'M'})[1]['lines'][0]['reason'],'VERIFIED')

    def test_delivery_list_batches_scopes_and_retains_line_labels(self):
        self.counted('S',10)
        self.counted('B',5)
        self.api('deliveries/preflight',self.doc('M'))
        for i in range(12):self.api('deliveries/preflight',self.doc('N'+str(i)))
        with veyra.transaction() as db:
            statements=[]
            db.set_trace_callback(statements.append)
            orders=veyra.list_data(db,'deliveries',{})
            db.set_trace_callback(None)
        self.assertEqual(len(orders),13)
        self.assertEqual([o['ref'] for o in orders],sorted([o['ref'] for o in orders],reverse=True))
        self.assertTrue(all([l['sku'] for l in o['lines']]==['S','B'] and
                            [l['evidence'] for l in o['lines']]==['CURRENT','CURRENT'] for o in orders))
        self.assertEqual(len([sql for sql in statements if sql.lstrip().upper().startswith(('SELECT','WITH'))]),3)
        _,started=self.api('counts/start',{'sku':'S','location':'WH/A'})
        self.api('counts/submit',{'session_id':started['session_id'],'qty':9})
        self.assertEqual(self.api('deliveries')[1][0]['lines'][0]['evidence'],'CONFLICT')
        self.api('movements',{'ref':'R','kind':'RECEIVE','sku':'B','location':'WH/A','qty':1})
        self.assertEqual([l['evidence'] for l in self.api('deliveries')[1][0]['lines']],['CONFLICT','STALE'])

    def test_invalid_lines_and_refresh(self):
        for doc in (self.doc(second=0),{'ref':'M','lines':[{'sku':'S','location':'WH/A','qty':1},{'sku':'BAD','location':'WH/A','qty':1}]},
                    {'ref':'M','lines':[{'sku':'S','location':'WH/A','qty':1},{'sku':'B','location':'BAD','qty':1}]}):
            self.assertNotEqual(self.api('deliveries/preflight',doc)[0],200)
            self.assertEqual(self.api('deliveries')[1],[])
        d=self.doc();self.api('deliveries/preflight',d)
        self.assertEqual(self.api('deliveries/preflight',self.doc(second=2))[0],409)
        self.assertEqual(self.api('deliveries/preflight',{'ref':'X','lines':[d['lines'][0],d['lines'][0]]})[0],409)
        lines=self.api('deliveries')[1][0]['lines']
        self.step('M','READY');self.step('M','START_PICKING')
        self.assertEqual(self.step('M','PICK',1,99999)[0],404)
        self.assertEqual(self.step('M','PICK',-1,lines[0]['id'])[0],400)
        self.assertEqual(self.step('M','PICK',5,lines[0]['id'])[0],409)
        self.assertEqual(self.api('deliveries')[1][0]['lines'][0]['picked_qty'],0)

if __name__=='__main__':unittest.main()
