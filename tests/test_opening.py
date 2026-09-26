"""Opening checkpoints establish a replay boundary, not a physical or historical claim."""
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

import veyra

ROOT=Path(__file__).resolve().parents[1]


def replay(db, product_id, location_id):
    """Independently replay a complete per-scope version chain after its checkpoint."""
    anchor=veyra.one(db, '''SELECT * FROM opening_balances
        WHERE product_id=? AND location_id=?''', (product_id,location_id))
    assert anchor['kind']=='OPENING_BALANCE'
    qty,version=anchor['qty'],anchor['version']
    movements=veyra.rows(db, '''SELECT * FROM movements WHERE product_id=? AND id>?
        AND (source_id=? OR dest_id=?) ORDER BY id''',
        (product_id,anchor['after_movement_id'],location_id,location_id))
    for m in movements:
        source=m['source_id']==location_id
        resulting=m['source_version'] if source else m['dest_version']
        assert resulting==version+1, (m['ref'],version,resulting)
        if m['kind']=='RECEIVE': qty+=m['qty']
        elif m['kind']=='TRANSFER': qty+=-m['qty'] if source else m['qty']
        elif m['kind']=='DELIVER': qty-=m['qty']
        elif m['kind']=='ADJUST': qty=m['qty']
        else: raise AssertionError(m['kind'])
        version=resulting
    return (qty,version),anchor,movements


class Opening(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.original=veyra.DB
        veyra.DB=os.path.join(self.folder.name,'inventory.sqlite3')
    def tearDown(self):
        veyra.DB=self.original
        self.folder.cleanup()

    def test_fresh_seed_and_subsequent_movements_replay(self):
        env={**os.environ,'VEYRA_DB':veyra.DB}
        for _ in range(2):
            subprocess.run([sys.executable,'seed.py'],cwd=ROOT,env=env,check=True,capture_output=True)
        with veyra.transaction() as db:
            self.assertEqual(veyra.one(db,'SELECT COUNT(*) n FROM opening_balances')['n'],2)
            for product,initial in ((1,768),(2,5)):
                result,anchor,moves=replay(db,product,1)
                self.assertEqual((result,anchor['qty'],anchor['version'],anchor['after_movement_id'],moves),
                                 ((initial,0),initial,0,0,[]))
            db.execute("INSERT INTO users(id,username,salt,hash) VALUES(1,'worker','salt','hash')")
            veyra.movement(db,{'kind':'RECEIVE','ref':'R','sku':'S','location':'WH/A','qty':3},1)
            veyra.movement(db,{'kind':'ADJUST','ref':'A','sku':'S','location':'WH/A','qty':760},1)
            db.execute("INSERT INTO locations(warehouse_id,code,name) VALUES(1,'B','Bin B')")
            veyra.movement(db,{'kind':'TRANSFER','ref':'T','sku':'S','location':'WH/A',
                'destination':'WH/B','qty':2},1)
        with closing(veyra.connect()) as db:
            actual=veyra.one(db,'SELECT qty,version FROM stock WHERE product_id=1 AND location_id=1')
            result,anchor,moves=replay(db,1,1)
            self.assertEqual((result,[m['ref'] for m in moves],(actual['qty'],actual['version'])),
                             ((758,3),['R','A','T'],(758,3)))
            self.assertEqual(replay(db,1,2)[0],(2,1))
            self.assertEqual(replay(db,1,2)[1]['qty'],0)

    def legacy_fixture(self):
        veyra.init()
        with veyra.transaction() as db:
            # Model an installation predating opening checkpoints and P2 lines.
            db.execute('DROP TRIGGER opening_on_stock_insert')
            db.execute('DROP TABLE opening_balances')
            db.execute("INSERT INTO users(id,username,salt,hash) VALUES(1,'old','salt','hash')")
            db.execute("INSERT INTO products(id,sku,name) VALUES(1,'S','Steel')")
            db.execute("INSERT INTO warehouses(id,code,name) VALUES(1,'WH','Warehouse')")
            db.execute("INSERT INTO locations(id,warehouse_id,code,name) VALUES(1,1,'A','Bin')")
            db.execute('INSERT INTO stock VALUES(1,1,8,2)')
            db.execute("INSERT INTO movements(ref,kind,product_id,dest_id,qty,dest_version,actor) VALUES('OLD','RECEIVE',1,1,3,1,1)")
            db.execute("INSERT INTO movements(ref,kind,product_id,source_id,qty,source_version,actor) VALUES('OLD2','ADJUST',1,1,8,2,1)")
            db.execute('''INSERT INTO count_sessions(product_id,location_id,captured_version,captured_qty,actor,status)
                VALUES(1,1,2,8,1,'SUBMITTED')''')
            db.execute("INSERT INTO evidence(session_id,product_id,location_id,observed_qty,captured_version,actor,status) VALUES(1,1,1,8,2,1,'VERIFIED')")
            db.execute("INSERT INTO deliveries(ref,product_id,location_id,qty,state,actor) VALUES('D',1,1,2,'PACKED',1)")
            db.execute('DROP TABLE delivery_lines')

    def test_upgrade_preserves_evidence_version_and_replays_from_checkpoint(self):
        self.legacy_fixture()
        for _ in range(2): veyra.init()
        with veyra.transaction() as db:
            result,anchor,moves=replay(db,1,1)
            self.assertEqual((result,anchor['qty'],anchor['version'],anchor['after_movement_id'],moves),
                             ((8,2),8,2,2,[]))
            self.assertEqual(veyra.one(db,'SELECT COUNT(*) n FROM opening_balances')['n'],1)
            self.assertEqual(veyra.one(db,'SELECT qty,version FROM stock'),{'qty':8,'version':2})
            self.assertEqual(veyra.one(db,'SELECT observed_qty,captured_version FROM evidence'),
                             {'observed_qty':8,'captured_version':2})
            self.assertEqual(veyra.one(db,'SELECT captured_qty,captured_version FROM count_sessions'),
                             {'captured_qty':8,'captured_version':2})
            p,l,s=veyra.scope(db,'S','WH/A')
            decision,eid=veyra.decide(db,'D',p,l,s,2,1,'COMMIT')
            self.assertEqual((decision['reason'],eid),('VERIFIED',1))
            veyra.movement(db,{'kind':'RECEIVE','ref':'NEW','sku':'S','location':'WH/A','qty':2},1)
            self.assertEqual(replay(db,1,1)[0],(10,3))
            self.assertEqual(veyra.decide(db,'D',p,l,veyra.scope(db,'S','WH/A')[2],2,1,'COMMIT')[0]['reason'],
                             'STALE_PHYSICAL_EVIDENCE')

    def test_upgrade_failure_rolls_back_schema_and_checkpoint(self):
        self.legacy_fixture()
        # Force failure on the second opening insert after P2 schema has been built.
        with veyra.transaction() as db:
            db.execute("INSERT INTO products(id,sku,name) VALUES(2,'B','Brass')")
            db.execute('INSERT INTO stock VALUES(2,1,5,0)')
            db.execute('''CREATE TABLE opening_balances(product_id INTEGER NOT NULL,location_id INTEGER NOT NULL,
                kind TEXT NOT NULL DEFAULT 'OPENING_BALANCE' CHECK(kind='OPENING_BALANCE'),
                qty INTEGER NOT NULL CHECK(qty>=0),version INTEGER NOT NULL,
                after_movement_id INTEGER NOT NULL,recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(product_id,location_id),
                FOREIGN KEY(product_id,location_id) REFERENCES stock(product_id,location_id))''')
            db.execute('''CREATE TRIGGER fail_open BEFORE INSERT ON opening_balances
                WHEN NEW.product_id=2 BEGIN SELECT RAISE(ABORT,'injected opening failure'); END''')
        with self.assertRaises(Exception): veyra.init()
        with closing(veyra.connect()) as db:
            self.assertIsNone(veyra.one(db,"SELECT name FROM sqlite_master WHERE name='delivery_lines'"))
            self.assertFalse(veyra.one(db,"SELECT name FROM sqlite_master WHERE name='opening_on_stock_insert'"))
            self.assertEqual(veyra.rows(db,'SELECT qty,version FROM stock ORDER BY product_id'),
                             [{'qty':8,'version':2},{'qty':5,'version':0}])
            self.assertEqual(veyra.one(db,'SELECT COUNT(*) n FROM opening_balances')['n'],0)
        with veyra.transaction() as db: db.execute('DROP TRIGGER fail_open')
        veyra.init()
        with closing(veyra.connect()) as db:
            self.assertEqual(replay(db,1,1)[0],(8,2))
            self.assertEqual(replay(db,2,1)[0],(5,0))


if __name__=='__main__': unittest.main()
