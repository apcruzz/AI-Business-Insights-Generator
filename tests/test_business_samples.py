"""Load demo files through the real upload pipeline and verify chart readiness."""
import json
import unittest
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
from backend.data_loader import frame_from_payload
from backend.normalizer import normalize, suggest_mapping

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT/'data/sample_catalog.json').read_text())
REQUIRED = {
    'Cafe': ['Date','category','weather'],
    'Restaurant': ['product','Gross_Profit','category','Hour'],
    'Retail store': ['category','product','Quantity','Gross_Profit'],
    'Tech store': ['category','product','Quantity','Gross_Profit'],
    'Furniture shop': ['category','product','Gross_Profit','delivery'],
    'Bakery': ['Hour','Quantity','product','waste','Date'],
    'Online shop': ['channel','product','Quantity','orders'],
    'Salon / barbershop': ['product','bookings','utilization'],
    'Repair / service shop': ['product','turnaround','jobStatus'],
}

class BusinessSampleTests(unittest.TestCase):
    def test_every_business_demo_loads_with_preferred_chart_data(self):
        self.assertEqual({sample['business'] for sample in CATALOG}, set(REQUIRED))
        self.assertEqual(len(CATALOG),len(REQUIRED))
        for sample in CATALOG:
            with self.subTest(business=sample['business']):
                frame, name, _ = frame_from_payload({'sample':sample['filename']})
                result = normalize(frame,suggest_mapping(frame.columns),sample['business'])
                self.assertEqual(name,sample['filename'])
                self.assertGreater(len(result['rows']),100)
                self.assertTrue(frame['Data_Type'].eq('Fictional demonstration data').all())
                self.assertTrue(result['capabilities']['orders'])
                for cap in REQUIRED[sample['business']]:
                    self.assertTrue(result['capabilities'][cap],cap)
                normalized=pd.DataFrame(result['rows'])
                self.assertGreater(normalized['Net_Sales'].sum(),0)
                self.assertGreater(normalized['Product_Name'].nunique(),3)
                self.assertGreater(normalized['Date'].nunique(),20)
                self.assertTrue((normalized['Gross_Sales']-normalized['Discount_Amount']-normalized['Net_Sales']).abs().lt(.011).all())
                self.assertTrue((normalized['Net_Sales']-normalized['Total_COGS']-normalized['Gross_Profit']).abs().lt(.011).all())

    def test_operational_examples_have_meaningful_variation(self):
        furniture=pd.read_csv(ROOT/'data/samples/Furniture_Demo.csv')
        self.assertEqual(set(furniture.Delivery_Status),{'On time','Late'})
        self.assertLess(furniture.Delivery_ID.nunique(),len(furniture))
        self.assertTrue((furniture.groupby('Delivery_ID').Delivery_Status.nunique()==1).all())
        bakery=pd.read_csv(ROOT/'data/samples/Bakery_Demo.csv')
        self.assertGreater(bakery.Waste_Cost.sum(),0)
        online=pd.read_csv(ROOT/'data/samples/Online_Shop_Demo.csv')
        self.assertGreaterEqual(online.Sales_Channel.nunique(),3)
        self.assertGreater(online.groupby('Transaction_ID').Net_Sales.sum().nunique(),10)
        salon=pd.read_csv(ROOT/'data/samples/Salon_Demo.csv')
        self.assertTrue({'Completed','Cancelled','No-show'} <= set(salon.Appointment_Status))
        for (_, day), rows in salon.groupby(['Employee_Name','Date']):
            self.assertEqual(rows.Available_Minutes.nunique(),1)
            self.assertLessEqual(rows.Appointment_Minutes.sum(),rows.Available_Minutes.iloc[0])
            # Use Python datetime, matching the application and avoiding pandas
            # datetime inference issues with this project's Python 3.14 environment.
            stamps=[datetime.fromisoformat(value) for value in rows.Appointment_Start]
            ends=[stamp+timedelta(minutes=int(minutes)) for stamp,minutes in zip(stamps,rows.Appointment_Minutes)]
            self.assertTrue(all(ends[i]<=stamps[i+1] for i in range(len(rows)-1)))
        repair=pd.read_csv(ROOT/'data/samples/Repair_Shop_Demo.csv')
        self.assertGreaterEqual(repair.Job_Status.nunique(),4)
        open_jobs=repair.Job_Status!='Completed'
        self.assertTrue(repair.loc[open_jobs,'Job_Completed'].isna().all())
        self.assertTrue(repair.loc[open_jobs,'Net_Sales'].eq(0).all())
