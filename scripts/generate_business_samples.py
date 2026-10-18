"""Regenerate the eleven fictional demos: python scripts/generate_business_samples.py.

Uses only the standard library and fixed random seeds. These are illustrative
patterns, not claims about real shops. Original sample files are left untouched.
"""
import csv
import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from random import Random

ROOT = Path(__file__).resolve().parents[1]
START = date(2026, 8, 1)
DAYS = 61
# name, category, unit selling price, direct unit cost (all money is USD).
PRODUCTS = {
    'Cafe': [('Latte','Coffee',5.5,1.6),('Americano','Coffee',3.5,.65),('Iced coffee','Cold drinks',4.75,1.2),('Matcha latte','Cold drinks',5.75,1.9),('Butter croissant','Pastries',3.8,1.35),('Blueberry muffin','Pastries',3.5,1.1),('Ham toastie','Snacks',7.5,3.1)],
    'Restaurant': [('Chicken rice bowl','Mains',13.5,4.6),('Fish tacos','Mains',15,5.7),('Mushroom pasta','Mains',16,5.2),('Garden salad','Sides',7,2.3),('Loaded fries','Sides',8.5,2.8),('Lemonade','Drinks',4,.8),('Chocolate brownie','Desserts',5.5,1.7)],
    'Retail store': [('Cotton tee','Tops',22,8),('Linen shirt','Tops',48,21),('Straight jeans','Bottoms',65,30),('Summer skirt','Bottoms',38,16),('Canvas tote','Accessories',18,5),('Everyday cap','Accessories',20,7),('Knit cardigan','Layers',58,26)],
    'Tech store': [('Everyday laptop','Computers',799,655),('Tablet 10 inch','Tablets',329,245),('Wireless earbuds','Audio',69,28),('Portable speaker','Audio',89,42),('USB-C charger','Accessories',25,8),('Braided cable','Accessories',12,3),('Wireless mouse','Accessories',35,12)],
    'Furniture shop': [('Oak dining table','Dining',650,360),('Dining chair','Dining',115,56),('Compact sofa','Living room',890,520),('Accent chair','Living room',280,145),('Storage bed','Bedroom',720,390),('Bedside table','Bedroom',95,44),('Standing desk','Office',420,230),('Office chair','Office',210,105)],
    'Bakery': [('Sourdough loaf','Bread',6.5,2.1),('Baguette','Bread',3.5,1.1),('Butter croissant','Pastries',3.8,1.3),('Cinnamon roll','Pastries',4.5,1.45),('Chocolate cookie','Cookies',2.5,.65),('Lemon slice','Cakes',5,1.7)],
    'Online shop': [('Canvas tote','Bags',18,5),('Travel backpack','Bags',65,28),('Steel bottle','Drinkware',24,9),('Travel mug','Drinkware',19,7),('Desk organizer','Home',32,12),('Notebook set','Stationery',14,4),('Planner','Stationery',22,7)],
    'Grocery store': [('Bananas (bunch)','Produce',2.8,1.7),('Apples (bag)','Produce',4.5,2.9),('Tomatoes 500 g','Produce',3.2,1.95),('Fresh milk 1 L','Dairy',3.6,2.65),('Eggs (dozen)','Dairy',4.8,3.5),('Rice 5 kg','Pantry',12.5,9.25),('Breakfast cereal','Pantry',5.9,3.8),('Wholemeal loaf','Bakery',3.5,2.05),('Frozen peas 500 g','Frozen foods',2.9,1.8),('Dish soap 500 mL','Household',3.9,2.15)],
    'Ice cream shop': [('Vanilla scoop','Ice cream',3.5,.95),('Chocolate scoop','Ice cream',3.75,1.1),('Strawberry scoop','Ice cream',3.75,1.15),('Salted caramel scoop','Ice cream',4,1.2),('Cookies and cream scoop','Ice cream',4,1.3),('Mango sorbet scoop','Sorbet',4,1.1),('Chocolate sundae','Sundaes',6.5,2.1),('Strawberry milkshake','Shakes',6,1.9)],
}


def sales_line(order, stamp, product, quantity, employee, rng, line=1, discount=True):
    """Keep money internally consistent at line level, with cents rounded once."""
    name, category, price, unit_cost = product
    gross = round(quantity * price, 2)
    reduction = round(gross * (.1 if discount and rng.random() < .16 else 0), 2)
    net = round(gross - reduction, 2)
    cost = round(quantity * unit_cost, 2)
    return dict(Transaction_ID=order, Line_ID=f'{order}-{line}', Date=stamp.date().isoformat(), Time=stamp.strftime('%H:%M:%S'),
                Hour=stamp.hour, Product_Name=name, Category=category, Quantity=quantity, Unit_Price=price,
                Gross_Sales=gross, Discount_Amount=reduction, Net_Sales=net, Unit_COGS=unit_cost, Total_COGS=cost,
                Gross_Profit=round(net-cost, 2), Employee_Name=employee, Store_Location='Fictional demo shop',
                Currency='USD', Data_Type='Fictional demonstration data')


def retail_sample(business, seed):
    rng = Random(seed)
    products = PRODUCTS[business]
    rows, sequence = [], 0
    for offset in range(DAYS):
        day = START + timedelta(days=offset)
        # One fictional weather label per day; never retrieve actual weather.
        weather = rng.choices(['Sunny','Cloudy','Rainy'], [5,3,2])[0]
        base = 5 if business == 'Furniture shop' else 8 if business in ('Retail store','Tech store') else 14
        orders = base + rng.randint(0,5) + (4 if day.weekday() >= 5 else 0) + offset // 24
        if business == 'Grocery store': orders += 4
        for _ in range(orders):
            sequence += 1
            hour = rng.choice([7,8,8,9,10,12,13,15,16]) if business in ('Cafe','Bakery') else rng.choice([11,12,12,13,14,17,18,18,19,20]) if business == 'Restaurant' else rng.randint(10,18)
            if business == 'Grocery store': hour = rng.choice([8,9,10,12,15,17,17,18,18,19,20])
            if business == 'Ice cream shop': hour = rng.choice([11,12,13,14,14,15,15,16,16,17,18,19,20])
            stamp = datetime.combine(day,time(hour,rng.randrange(60)))
            order = f'DEMO-{seed}-{sequence:05}'
            employee = rng.choice(['Alex Demo','Jamie Demo','Riley Demo'])
            payment = rng.choice(['Card','Mobile pay','Cash'])
            channel = rng.choices(['Website','Marketplace','Social shop'],[6,3,2])[0]
            due = day + timedelta(days=5+rng.randrange(8))
            late = rng.random() < (.3 if offset < 31 else .16)
            delivered = due + timedelta(days=rng.randint(1,3) if late else -rng.randrange(2))
            # Several products can share an order or delivery; their totals remain line-level.
            # Grocery baskets contain several packaged items; quantity counts packs/servings,
            # not weight. Keep earlier businesses' random sequences unchanged.
            line_count = rng.choices([2,3,4,5],[2,4,3,1])[0] if business == 'Grocery store' else rng.choices([1,2,3],[5,4,1])[0]
            for line, product in enumerate(rng.sample(products,line_count),1):
                quantity = rng.choices([1,2,3,4],[7,3,1,1])[0]
                row = sales_line(order,stamp,product,quantity,employee,rng,line)
                row['Payment_Method'] = payment
                if business in ('Cafe', 'Ice cream shop'): row['Weather'] = weather
                if business == 'Online shop': row['Sales_Channel'] = channel
                if business == 'Furniture shop':
                    row.update(Delivery_ID=f'D-{sequence:05}',Delivery_Status='Late' if late else 'On time',
                               Delivery_Due=due.isoformat(),Delivered_At=delivered.isoformat())
                if business == 'Bakery':
                    # Occasional line-level waste costs, rather than repeated daily totals.
                    row['Waste_Cost'] = round(product[3] * rng.choice([1,1,2,3]),2) if rng.random()<.18 else 0
                rows.append(row)
    return rows


def salon_sample():
    rng = Random(208)
    # Duration is in minutes; non-overlapping appointments fit within the daily shift.
    services = [('Classic haircut','Hair',30,4,30),('Wash and style','Hair',40,6,45),('Hair color','Color',95,22,90),
                ('Beard trim','Grooming',18,2,15),('Hair treatment','Treatments',55,12,60)]
    rows, sequence = [], 0
    for offset in range(DAYS):
        day = START + timedelta(days=offset)
        if day.weekday()==6: continue
        for staff, available, target in [('Alex Demo',480,6),('Jamie Demo',420,5),('Riley Demo',360,4)]:
            cursor, end = datetime.combine(day,time(9)), datetime.combine(day,time(9)) + timedelta(minutes=available)
            for _ in range(target+rng.randint(-1,1)):
                service = rng.choice(services)
                if cursor + timedelta(minutes=service[4]) > end: break
                sequence += 1
                status = rng.choices(['Completed','Cancelled','No-show'],[90,7,3])[0]
                row = sales_line(f'SAL-{sequence:05}',cursor,service[:4],1 if status=='Completed' else 0,staff,rng,discount=False)
                row.update(Appointment_ID=f'A-{sequence:05}',Appointment_Start=cursor.isoformat(),Appointment_Status=status,
                           Appointment_Minutes=service[4],Available_Minutes=available,Payment_Method='Card')
                rows.append(row)
                cursor += timedelta(minutes=service[4]+rng.choice([0,15,30]))
    return rows


def repair_sample():
    rng = Random(209)
    services = [('Screen replacement','Phone repair',120,50,8),('Battery replacement','Phone repair',70,22,4),
                ('Laptop diagnostics','Computer service',45,6,12),('Laptop repair','Computer service',180,65,72),
                ('Console repair','Electronics service',95,28,48),('Device cleaning','Maintenance',35,4,3)]
    rows, sequence = [], 0
    for offset in range(DAYS):
        day = START + timedelta(days=offset)
        for _ in range(rng.randint(4,9)):
            sequence += 1
            service = rng.choice(services)
            opened = datetime.combine(day,time(rng.randint(9,16),rng.choice([0,15,30,45])))
            status = 'Completed' if offset<50 else rng.choices(['Completed','In progress','Waiting for parts','Queued'],[5,2,2,1])[0]
            completed = opened + timedelta(hours=service[4]+rng.randint(0,24)) if status=='Completed' else None
            row = sales_line(f'REP-{sequence:05}',completed or opened,service[:4],1 if completed else 0,rng.choice(['Alex Demo','Sam Demo','Taylor Demo']),rng)
            row.update(Job_ID=f'J-{sequence:05}',Job_Status=status,Job_Opened=opened.isoformat(),
                       Job_Completed=completed.isoformat() if completed else '',Payment_Method='Card')
            rows.append(row)
    return rows


def generate():
    """Write only the named demo files, retaining the original sample collection."""
    catalog=json.loads((ROOT/'data/sample_catalog.json').read_text())
    for index, entry in enumerate(catalog):
        business=entry['business']
        rows=salon_sample() if business=='Salon / barbershop' else repair_sample() if business=='Repair / service shop' else retail_sample(business,201+index)
        path=ROOT/'data/samples'/entry['filename']
        with path.open('w',newline='') as handle:
            writer=csv.DictWriter(handle,fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        print(f'{entry["filename"]}: {len(rows)} fictional rows')


if __name__=='__main__':
    generate()
