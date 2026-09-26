"""Initialize a NEW local database with synthetic demo data; never resets user data."""
import veyra
veyra.init()
with veyra.transaction() as db:
    if db.execute('SELECT COUNT(*) FROM products').fetchone()[0]:
        print('Existing products found; seed skipped (no data overwritten).')
    else:
        db.execute("INSERT INTO categories(name) VALUES('Components')")
        db.execute("INSERT INTO products(sku,name,category_id,reorder_point) VALUES('S','Steel bracket',1,4)")
        db.execute("INSERT INTO warehouses(code,name) VALUES('WH','Main warehouse')")
        db.execute("INSERT INTO locations(warehouse_id,code,name) VALUES(1,'A','Bin A')")
        db.execute('INSERT INTO stock(product_id,location_id,qty,version) VALUES(1,1,768,0)')
        print('Demo initialized: S / WH/A = 768 at v0. Sign up in the browser.')
