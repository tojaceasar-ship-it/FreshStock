from app.core.database import SessionLocal
from app.models.user import User, UserRole
from app.models.category import Category
from app.models.supplier import Supplier
from app.models.product import Product, ProductUnit, ProductSupplier
from app.models.location import WarehouseLocation, LocationType
from app.models.batch import Batch
from app.models.stock import Stock
from app.models.delivery import Delivery, DeliveryItem, DeliveryStatus
from app.models.sale import Sale, SaleItem, SaleSource
from app.models.waste import Waste, WasteReason
from app.core.security import get_password_hash
from datetime import datetime, date, timedelta
import random
import os
from decimal import Decimal
from sqlalchemy import func

def seed():
    db = SessionLocal()
    try:
        # Clear existing data in correct order
        print("Clearing existing data...")
        db.query(Waste).delete()
        db.query(SaleItem).delete()
        db.query(Sale).delete()
        db.query(DeliveryItem).delete()
        db.query(Delivery).delete()
        db.query(Stock).delete()
        db.query(Batch).delete()
        db.query(ProductSupplier).delete()
        db.query(Product).delete()
        db.query(Category).delete()
        db.query(Supplier).delete()
        db.query(WarehouseLocation).delete()
        db.query(User).delete()
        db.commit()
        
        # Users
        print("Seeding users...")
        password_names = ["DEMO_OWNER_PASSWORD", "DEMO_MANAGER_PASSWORD", "DEMO_WAREHOUSE_PASSWORD", "DEMO_EMPLOYEE_PASSWORD"]
        missing = [name for name in password_names if not os.getenv(name)]
        if missing:
            raise RuntimeError(f"Ustaw silne hasła demo przed seedem: {', '.join(missing)}")
        users = [
            User(email="owner@freshstock.pl", username="owner", hashed_password=get_password_hash(os.environ["DEMO_OWNER_PASSWORD"]), full_name="Jan Właściciel", role=UserRole.OWNER, is_active=True),
            User(email="manager@freshstock.pl", username="manager", hashed_password=get_password_hash(os.environ["DEMO_MANAGER_PASSWORD"]), full_name="Anna Kowalska", role=UserRole.MANAGER, is_active=True),
            User(email="warehouse@freshstock.pl", username="warehouse", hashed_password=get_password_hash(os.environ["DEMO_WAREHOUSE_PASSWORD"]), full_name="Marek Magazynier", role=UserRole.WAREHOUSE, is_active=True),
            User(email="employee@freshstock.pl", username="employee", hashed_password=get_password_hash(os.environ["DEMO_EMPLOYEE_PASSWORD"]), full_name="Ewa Pracownik", role=UserRole.EMPLOYEE, is_active=True),
        ]
        db.add_all(users)
        db.commit()
        
        # Categories
        print("Seeding categories...")
        categories_data = [
            ("Nabiał", "Mleko, jogurty, sery", "#3B82F6"),
            ("Pieczywo", "Chleb, bułki, ciasta", "#F59E0B"),
            ("Napoje", "Woda, soki, napoje gazowane", "#10B981"),
            ("Mięso", "Wędliny, mięso świeże", "#EF4444"),
            ("Warzywa i Owoce", "Świeże warzywa i owoce", "#22C55E"),
            ("Mrożonki", "Produkty mrożone", "#06B6D4"),
            ("Słodycze", "Czekolady, ciastka", "#EC4899"),
            ("Chemia", "Chemia domowa", "#8B5CF6"),
            ("Konserwy", "Konserwy i przetwory", "#F97316"),
            ("Przekąski", "Chipsy, orzechy", "#EAB308"),
        ]
        categories = []
        for name, desc, color in categories_data:
            cat = Category(name=name, description=desc, color=color)
            db.add(cat)
            categories.append(cat)
        db.commit()
        for cat in categories:
            db.refresh(cat)
        
        # Suppliers
        print("Seeding suppliers...")
        suppliers_data = [
            ("Mlekovita", "mlekovita@example.pl", "123456789", "Nabiał", 1),
            ("Bakery Fresh", "bakery@example.pl", "987654321", "Pieczywo", 1),
            ("Coca-Cola HBC", "coke@example.pl", "555666777", "Napoje", 2),
            ("Sokołów", "sokolow@example.pl", "111222333", "Mięso", 2),
            ("Fresh Market", "fresh@example.pl", "444555666", "Warzywa", 1),
        ]
        suppliers = []
        for name, email, phone, notes, lead in suppliers_data:
            sup = Supplier(name=name, email=email, phone=phone, vat_number=f"PL{random.randint(1000000000,9999999999)}", contact_person=f"Kontakt {name}", payment_terms="14 dni", min_order_value=Decimal("200"), lead_time_days=lead, is_active=True, notes=notes)
            db.add(sup)
            suppliers.append(sup)
        db.commit()
        for sup in suppliers:
            db.refresh(sup)
        
        # Locations
        print("Seeding locations...")
        loc_data = [
            ("Sklep - Główny", "STORE-MAIN", LocationType.STORE, None),
            ("Magazyn", "WH-MAIN", LocationType.WAREHOUSE, None),
            ("Chłodnia", "FRIDGE-01", LocationType.FRIDGE, None),
            ("Mroźnia", "FREEZER-01", LocationType.FREEZER, None),
            ("Regał A1", "SHELF-A1", LocationType.SHELF, None),
            ("Regał A2", "SHELF-A2", LocationType.SHELF, None),
            ("Regał B1", "SHELF-B1", LocationType.SHELF, None),
            ("Zaplecze", "BACK-01", LocationType.BACKROOM, None),
        ]
        locations = []
        for name, code, typ, parent in loc_data:
            loc = WarehouseLocation(name=name, code=code, type=typ, parent_id=parent)
            db.add(loc)
            locations.append(loc)
        db.commit()
        for loc in locations:
            db.refresh(loc)
        
        # Create hierarchy
        # Make shelves children of warehouse
        warehouse = next(l for l in locations if l.code == "WH-MAIN")
        for loc in locations:
            if loc.code.startswith("SHELF-"):
                loc.parent_id = warehouse.id
        db.commit()
        
        # Products - 50 products
        print("Seeding products...")
        products_data = [
            # Nabiał
            ("MLE-001", "5901234560001", "Mleko 1L 3.2%", "Mlekovita", categories[0].id, "l", 2.50, 3.99, 10, 30, 5, True, 7, suppliers[0].id),
            ("MLE-002", "5901234560002", "Jogurt Naturalny 400g", "Mlekovita", categories[0].id, "szt", 1.80, 2.99, 15, 40, 8, True, 5, suppliers[0].id),
            ("MLE-003", "5901234560003", "Ser Żółty Gouda 300g", "Mlekovita", categories[0].id, "szt", 5.20, 8.99, 8, 25, 4, True, 14, suppliers[0].id),
            ("MLE-004", "5901234560004", "Masło 200g", "Mlekovita", categories[0].id, "szt", 3.00, 5.49, 12, 35, 6, True, 10, suppliers[0].id),
            ("MLE-005", "5901234560005", "Śmietana 18% 200ml", "Mlekovita", categories[0].id, "szt", 1.50, 2.79, 10, 30, 5, True, 5, suppliers[0].id),
            # Pieczywo
            ("PIE-001", "5901234560006", "Chleb Pszenny 500g", "Bakery", categories[1].id, "szt", 2.00, 3.99, 5, 15, 3, True, 2, suppliers[1].id),
            ("PIE-002", "5901234560007", "Bułki Kajzerki 4szt", "Bakery", categories[1].id, "opak", 1.20, 2.49, 8, 20, 4, True, 2, suppliers[1].id),
            ("PIE-003", "5901234560008", "Chleb Razowy 400g", "Bakery", categories[1].id, "szt", 2.20, 4.29, 5, 15, 3, True, 3, suppliers[1].id),
            # Napoje
            ("NAP-001", "5901234560009", "Woda Mineralna 1.5L", "Cisowianka", categories[2].id, "szt", 1.00, 2.19, 20, 60, 10, False, 0, suppliers[2].id),
            ("NAP-002", "5901234560010", "Coca-Cola 1L", "Coca-Cola", categories[2].id, "szt", 2.80, 4.99, 15, 50, 8, False, 0, suppliers[2].id),
            ("NAP-003", "5901234560011", "Monster Mango 500ml", "Monster", categories[2].id, "szt", 3.50, 6.99, 12, 40, 6, False, 0, suppliers[2].id),
            ("NAP-004", "5901234560012", "Sok Pomarańczowy 1L", "Tymbark", categories[2].id, "szt", 2.20, 4.49, 10, 30, 5, True, 30, suppliers[2].id),
            ("NAP-005", "5901234560013", "Red Bull 250ml", "Red Bull", categories[2].id, "szt", 3.00, 5.99, 10, 35, 5, False, 0, suppliers[2].id),
            # Mięso
            ("MIE-001", "5901234560014", "Szynka Gotowana 200g", "Sokołów", categories[3].id, "szt", 4.50, 7.99, 8, 25, 4, True, 7, suppliers[3].id),
            ("MIE-002", "5901234560015", "Kiełbasa Śląska 300g", "Sokołów", categories[3].id, "szt", 5.00, 9.49, 6, 20, 3, True, 10, suppliers[3].id),
            ("MIE-003", "5901234560016", "Pierś z Kurczaka 1kg", "Sokołów", categories[3].id, "kg", 12.00, 19.99, 5, 15, 3, True, 3, suppliers[3].id),
            # Warzywa
            ("WAR-001", "5901234560017", "Pomidory 1kg", "Fresh", categories[4].id, "kg", 4.00, 7.99, 5, 15, 3, True, 5, suppliers[4].id),
            ("WAR-002", "5901234560018", "Ogórki 1kg", "Fresh", categories[4].id, "kg", 3.00, 5.99, 5, 15, 3, True, 5, suppliers[4].id),
            ("WAR-003", "5901234560019", "Jabłka 1kg", "Fresh", categories[4].id, "kg", 2.50, 4.99, 8, 20, 4, True, 14, suppliers[4].id),
            ("WAR-004", "5901234560020", "Banany 1kg", "Fresh", categories[4].id, "kg", 3.50, 6.49, 6, 18, 3, True, 7, suppliers[4].id),
            # Mrożonki
            ("MRO-001", "5901234560021", "Pizza Margherita 400g", "Dr Oetker", categories[5].id, "szt", 4.00, 8.99, 8, 25, 4, True, 180, suppliers[0].id),
            ("MRO-002", "5901234560022", "Frytki 1kg", "Aviko", categories[5].id, "szt", 3.50, 7.49, 6, 20, 3, True, 180, suppliers[0].id),
            ("MRO-003", "5901234560023", "Lody Waniliowe 1L", "Koral", categories[5].id, "szt", 6.00, 12.99, 5, 15, 3, True, 90, suppliers[0].id),
            # Słodycze
            ("SLO-001", "5901234560024", "Czekolada Milka 100g", "Milka", categories[6].id, "szt", 2.00, 4.29, 15, 50, 8, False, 0, suppliers[2].id),
            ("SLO-002", "5901234560025", "Ciastka Oreo 176g", "Oreo", categories[6].id, "szt", 3.00, 5.99, 12, 40, 6, False, 0, suppliers[2].id),
            ("SLO-003", "5901234560026", "Żelki Haribo 200g", "Haribo", categories[6].id, "szt", 2.50, 4.99, 10, 35, 5, False, 0, suppliers[2].id),
            # Chemia
            ("CHE-001", "5901234560027", "Płyn do Naczyń 500ml", "Ludwik", categories[7].id, "szt", 3.00, 5.99, 8, 25, 4, False, 0, suppliers[4].id),
            ("CHE-002", "5901234560028", "Proszek do Prania 3kg", "Persil", categories[7].id, "szt", 15.00, 28.99, 5, 15, 3, False, 0, suppliers[4].id),
            # Konserwy
            ("KON-001", "5901234560029", "Tuńczyk w Sosie 170g", "Lisner", categories[8].id, "szt", 3.50, 6.49, 10, 30, 5, False, 0, suppliers[4].id),
            ("KON-002", "5901234560030", "Kukurydza 400g", "Bonduelle", categories[8].id, "szt", 2.00, 3.99, 12, 35, 6, False, 0, suppliers[4].id),
            # Przekąski
            ("PRZ-001", "5901234560031", "Chipsy Lay's 140g", "Lay's", categories[9].id, "szt", 2.80, 5.49, 12, 40, 6, False, 0, suppliers[2].id),
            ("PRZ-002", "5901234560032", "Orzeszki Ziemne 200g", "Felix", categories[9].id, "szt", 3.20, 6.29, 10, 30, 5, False, 0, suppliers[2].id),
            # More products to reach 50
            ("MLE-006", "5901234560033", "Kefir 400g", "Mlekovita", categories[0].id, "szt", 1.60, 2.89, 10, 30, 5, True, 5, suppliers[0].id),
            ("MLE-007", "5901234560034", "Serek Wiejski 200g", "Mlekovita", categories[0].id, "szt", 1.80, 3.29, 10, 30, 5, True, 7, suppliers[0].id),
            ("NAP-006", "5901234560035", "Woda Gazowana 1.5L", "Cisowianka", categories[2].id, "szt", 1.00, 2.19, 15, 50, 8, False, 0, suppliers[2].id),
            ("NAP-007", "5901234560036", "Sok Jabłkowy 1L", "Tymbark", categories[2].id, "szt", 2.20, 4.49, 10, 30, 5, True, 30, suppliers[2].id),
            ("MIE-004", "5901234560037", "Parówki 250g", "Sokołów", categories[3].id, "szt", 3.50, 6.49, 8, 25, 4, True, 7, suppliers[3].id),
            ("WAR-005", "5901234560038", "Marchew 1kg", "Fresh", categories[4].id, "kg", 2.00, 3.99, 5, 15, 3, True, 14, suppliers[4].id),
            ("WAR-006", "5901234560039", "Sałata Lodowa 1szt", "Fresh", categories[4].id, "szt", 2.50, 4.99, 5, 15, 3, True, 5, suppliers[4].id),
            ("SLO-004", "5901234560040", "Baton Snickers 50g", "Mars", categories[6].id, "szt", 1.20, 2.49, 20, 60, 10, False, 0, suppliers[2].id),
            ("SLO-005", "5901234560041", "Cukierki Mieszane 1kg", "Wawel", categories[6].id, "kg", 12.00, 22.99, 5, 15, 3, False, 0, suppliers[2].id),
            ("PRZ-003", "5901234560042", "Paluszki 200g", "Lajkonik", categories[9].id, "szt", 2.00, 3.99, 10, 30, 5, False, 0, suppliers[2].id),
            ("CHE-003", "5901234560043", "Papier Toaletowy 8szt", "Regina", categories[7].id, "opak", 8.00, 15.99, 6, 20, 3, False, 0, suppliers[4].id),
            ("KON-003", "5901234560044", "Fasola w Sosie 400g", "Heinz", categories[8].id, "szt", 2.20, 4.29, 10, 30, 5, False, 0, suppliers[4].id),
            ("MRO-004", "5901234560045", "Warzywa Mrożone 1kg", "Hortex", categories[5].id, "szt", 4.50, 8.99, 6, 20, 3, True, 180, suppliers[0].id),
            ("PIE-004", "5901234560046", "Drożdżówka 80g", "Bakery", categories[1].id, "szt", 1.50, 2.99, 5, 15, 3, True, 1, suppliers[1].id),
            ("MLE-008", "5901234560047", "Jogurt Owocowy 150g", "Mlekovita", categories[0].id, "szt", 1.20, 2.19, 15, 40, 8, True, 7, suppliers[0].id),
            ("NAP-008", "5901234560048", "Herbata Lipton 100szt", "Lipton", categories[2].id, "opak", 8.00, 15.99, 8, 25, 4, False, 0, suppliers[2].id),
            ("MIE-005", "5901234560049", "Salami 100g", "Sokołów", categories[3].id, "szt", 4.00, 7.49, 6, 20, 3, True, 21, suppliers[3].id),
            ("WAR-007", "5901234560050", "Ziemniaki 2kg", "Fresh", categories[4].id, "kg", 3.00, 5.99, 8, 20, 4, True, 14, suppliers[4].id),
        ]
        
        products = []
        for sku, ean, name, brand, cat_id, unit, pur_price, sell_price, min_s, target_s, safety_s, req_exp, warn_days, sup_id in products_data:
            prod = Product(
                sku=sku, ean=ean, name=name, brand=brand, category_id=cat_id,
                unit=ProductUnit(unit) if unit in [e.value for e in ProductUnit] else ProductUnit.PCS,
                vat_rate=Decimal("23.00"), purchase_price=Decimal(str(pur_price)), selling_price=Decimal(str(sell_price)),
                min_stock=min_s, target_stock=target_s, safety_stock=safety_s, is_active=True,
                default_supplier_id=sup_id, requires_expiry_control=req_exp, expiry_warning_days=warn_days
            )
            db.add(prod)
            products.append(prod)
        db.commit()
        for p in products:
            db.refresh(p)
        
        # Product-supplier links
        for p in products:
            if p.default_supplier_id:
                ps = ProductSupplier(product_id=p.id, supplier_id=p.default_supplier_id, purchase_price=p.purchase_price, is_preferred=True)
                db.add(ps)
        db.commit()
        
        # Batches with various expiry dates
        print("Seeding batches...")
        today = date.today()
        batches = []
        for product in products:
            # Random number of batches 1-3
            num_batches = random.randint(1, 3)
            for i in range(num_batches):
                # Expiry logic
                if not product.requires_expiry_control:
                    expiry = None
                else:
                    # Create some expired, some today, some soon
                    rand = random.random()
                    if rand < 0.1:  # 10% expired
                        expiry = today - timedelta(days=random.randint(1, 5))
                    elif rand < 0.15:  # 5% today
                        expiry = today
                    elif rand < 0.25:  # 10% in 1-3 days
                        expiry = today + timedelta(days=random.randint(1, 3))
                    elif rand < 0.4:  # 15% in 4-7 days
                        expiry = today + timedelta(days=random.randint(4, 7))
                    elif rand < 0.6:  # 20% in 8-14 days
                        expiry = today + timedelta(days=random.randint(8, 14))
                    else:
                        expiry = today + timedelta(days=random.randint(15, 90))
                
                qty_received = random.randint(10, 50)
                # Some batches partially sold
                qty_available = qty_received
                if random.random() < 0.3:
                    qty_available = random.randint(0, qty_received)
                
                # Low stock simulation for some products
                if random.random() < 0.15:
                    qty_available = random.randint(0, 3)
                
                batch = Batch(
                    product_id=product.id,
                    batch_number=f"BATCH-{product.sku}-{i+1}-{random.randint(100,999)}",
                    expiry_date=expiry,
                    manufacture_date=today - timedelta(days=random.randint(5, 30)) if expiry else None,
                    quantity_received=qty_received,
                    quantity_available=qty_available,
                    purchase_price=product.purchase_price,
                    supplier_id=product.default_supplier_id,
                    warehouse_location_id=random.choice(locations).id
                )
                db.add(batch)
                batches.append(batch)
        db.commit()
        
        # Stock aggregation
        print("Seeding stock...")
        # Clear and recalc stock from batches
        db.query(Stock).delete()
        stock_map = {}
        for batch in batches:
            if batch.quantity_available <= 0:
                continue
            key = (batch.product_id, batch.warehouse_location_id)
            if key not in stock_map:
                stock_map[key] = 0
            stock_map[key] += batch.quantity_available
        
        for (prod_id, loc_id), qty in stock_map.items():
            if loc_id is None:
                continue
            stock = Stock(product_id=prod_id, location_id=loc_id, quantity=qty)
            db.add(stock)
        db.commit()
        
        # Deliveries
        print("Seeding deliveries...")
        for _ in range(10):
            sup = random.choice(suppliers)
            delivery = Delivery(
                supplier_id=sup.id,
                document_number=f"FV/{random.randint(1000,9999)}/{datetime.now().year}",
                status=DeliveryStatus.RECEIVED,
                total_value=Decimal(str(random.randint(200, 2000))),
                delivered_at=datetime.now() - timedelta(days=random.randint(0, 10)),
                created_by=users[0].id
            )
            db.add(delivery)
        db.commit()
        
        # Sales last 30 days
        print("Seeding sales...")
        for day_offset in range(30):
            sale_date = datetime.now() - timedelta(days=day_offset)
            num_sales_per_day = random.randint(1, 5)
            for _ in range(num_sales_per_day):
                sale = Sale(
                    sale_number=f"SALE-{sale_date.strftime('%Y%m%d')}-{random.randint(100,999)}",
                    sale_date=sale_date - timedelta(hours=random.randint(0,23)),
                    total_amount=Decimal("0"),
                    source=SaleSource.POS,
                    created_by=users[1].id
                )
                db.add(sale)
                db.flush()
                
                total = Decimal("0")
                num_items = random.randint(1, 5)
                for _ in range(num_items):
                    prod = random.choice(products)
                    qty = random.randint(1, 5)
                    # Check available stock
                    available = db.query(func.coalesce(func.sum(Batch.quantity_available), 0)).filter(Batch.product_id == prod.id).scalar() or 0
                    if available < qty:
                        continue
                    
                    # FEFO sale
                    remaining = qty
                    batches_prod = db.query(Batch).filter(Batch.product_id == prod.id, Batch.quantity_available > 0).order_by(Batch.expiry_date.asc().nulls_last()).all()
                    for b in batches_prod:
                        if remaining <= 0:
                            break
                        take = min(remaining, b.quantity_available)
                        b.quantity_available -= take
                        remaining -= take
                        
                        sale_item = SaleItem(
                            sale_id=sale.id,
                            product_id=prod.id,
                            batch_id=b.id,
                            quantity=take,
                            unit_price=prod.selling_price,
                            total_price=take * prod.selling_price
                        )
                        db.add(sale_item)
                        total += take * prod.selling_price
                
                sale.total_amount = total
                if total == 0:
                    db.delete(sale)
        db.commit()
        
        # Waste
        print("Seeding waste...")
        for _ in range(15):
            prod = random.choice(products)
            batch = db.query(Batch).filter(Batch.product_id == prod.id).first()
            if not batch:
                continue
            reason = random.choice(list(WasteReason))
            qty = random.randint(1, 5)
            waste = Waste(
                product_id=prod.id,
                batch_id=batch.id if random.random() > 0.3 else None,
                quantity=qty,
                purchase_value=prod.purchase_price * qty,
                sale_value=prod.selling_price * qty,
                reason=reason,
                notes=f"Test waste {reason.value}",
                reported_by=random.choice(users).id,
                location_id=random.choice(locations).id if locations else None
            )
            db.add(waste)
        db.commit()
        
        print("Seed completed successfully!")
        print(f"Users: {db.query(User).count()}")
        print(f"Products: {db.query(Product).count()}")
        print(f"Batches: {db.query(Batch).count()}")
        print(f"Stock entries: {db.query(Stock).count()}")
        
    except Exception as e:
        db.rollback()
        print(f"Seed error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    seed()
