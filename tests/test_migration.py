import os
import tempfile
import unittest
import veyra


class Migration(unittest.TestCase):
    def test_p1_database_upgraded_idempotently(self):
        with tempfile.TemporaryDirectory() as folder:
            original=veyra.DB
            try:
                veyra.DB=os.path.join(folder,'p1.sqlite3')
                veyra.init()
                db=veyra.connect()
                db.execute("INSERT INTO users(id,username,salt,hash) VALUES(1,'old','salt','hash')")
                db.execute("INSERT INTO products(id,sku,name) VALUES(1,'S','Steel')")
                db.execute("INSERT INTO warehouses(id,code,name) VALUES(1,'WH','Warehouse')")
                db.execute("INSERT INTO locations(id,warehouse_id,code,name) VALUES(1,1,'A','Bin')")
                db.execute("INSERT INTO stock VALUES(1,1,8,2)")
                db.execute("INSERT INTO deliveries(ref,product_id,location_id,qty,picked_qty,packed_qty,state,actor) VALUES('P1',1,1,4,4,2,'PACKING',1)")
                db.execute("INSERT INTO decisions(ref,stage,status,reason,current_version,stock_qty,actor) VALUES('P1','PREFLIGHT','ALLOWED','VERIFIED',2,8,1)")
                db.commit()
                db.execute('DROP TABLE delivery_lines')
                db.commit();db.close()
                for _ in range(2):veyra.init()
                db=veyra.connect()
                self.assertEqual(db.execute("SELECT qty,picked_qty,packed_qty FROM delivery_lines WHERE ref='P1'").fetchone()[:],(4,4,2))
                self.assertEqual(db.execute('SELECT COUNT(*) FROM delivery_lines').fetchone()[0],1)
                self.assertEqual(db.execute('SELECT COUNT(*) FROM decisions').fetchone()[0],1)
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
                db.close()
            finally:veyra.DB=original

    def test_legacy_order_and_decision_fk_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            original=veyra.DB
            try:
                veyra.DB=os.path.join(folder,'old.sqlite3')
                veyra.init()
                db=veyra.connect()
                db.execute('PRAGMA foreign_keys=OFF')
                db.executescript("""
                    DROP TABLE deliveries;
                    CREATE TABLE deliveries(ref TEXT PRIMARY KEY, product_id INTEGER REFERENCES products(id),
                        location_id INTEGER REFERENCES locations(id), qty INTEGER, contact TEXT,
                        state TEXT CHECK(state IN ('PENDING','DONE','CANCELED')),
                        actor INTEGER REFERENCES users(id), created_at TEXT DEFAULT CURRENT_TIMESTAMP);
                    INSERT INTO users(id,username,salt,hash) VALUES(1,'old','salt','hash');
                    INSERT INTO products(id,sku,name) VALUES(1,'S','Steel');
                    INSERT INTO warehouses(id,code,name) VALUES(1,'WH','Warehouse');
                    INSERT INTO locations(id,warehouse_id,code,name) VALUES(1,1,'A','Bin');
                    INSERT INTO deliveries(ref,product_id,location_id,qty,state,actor) VALUES('OLD',1,1,2,'PENDING',1);
                    INSERT INTO deliveries(ref,product_id,location_id,qty,state,actor) VALUES('DONE',1,1,1,'DONE',1);
                    INSERT INTO decisions(ref,stage,status,reason,current_version,stock_qty,actor)
                        VALUES('OLD','PREFLIGHT','BLOCKED','MISSING_PHYSICAL_EVIDENCE',0,0,1);
                """)
                db.close()
                veyra.init()
                db=veyra.connect()
                self.assertEqual([(r['ref'],r['state']) for r in db.execute('SELECT ref,state FROM deliveries ORDER BY ref')],[('DONE','DONE'),('OLD','DRAFT')])
                self.assertEqual(db.execute("SELECT picked_qty,packed_qty FROM deliveries WHERE ref='OLD'").fetchone()[:],(0,0))
                self.assertEqual(db.execute('SELECT ref FROM decisions').fetchone()[0],'OLD')
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
                db.close()
                veyra.init()
            finally:
                veyra.DB=original


if __name__=='__main__': unittest.main()
