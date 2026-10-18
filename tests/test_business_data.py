"""Operational chart capabilities must reflect valid, countable uploaded records."""
import unittest
import pandas as pd
from backend.normalizer import normalize, suggest_mapping

class BusinessDataTests(unittest.TestCase):
    def normalized(self, **columns):
        size=len(next(iter(columns.values())))
        frame=pd.DataFrame({'Net_Sales':[20]*size,'Product_Name':['Service']*size,**columns})
        return normalize(frame, {c:c for c in frame.columns}, 'Other business')

    def test_missing_operational_data_is_unavailable(self):
        c=self.normalized(Date=['2026-01-01'])['capabilities']
        for key in ['delivery','bookings','utilization','waste','turnaround','jobStatus','channel']:
            self.assertFalse(c[key],key)

    def test_delivery_outcomes_and_conflicting_ids(self):
        result=self.normalized(Delivery_ID=['D1','D1','D2'], Delivery_Due=['2026-01-02']*3, Delivered_At=['2026-01-02','2026-01-02','2026-01-03'])
        self.assertTrue(result['capabilities']['delivery'])
        self.assertEqual([r['Delivery_Outcome'] for r in result['rows']],['On time','On time','Late'])
        self.assertFalse(self.normalized(Delivery_ID=['D1','D1'],Delivery_Status=['On time','Late'])['capabilities']['delivery'])
        self.assertFalse(self.normalized(Delivery_ID=['D1'],Delivery_Status=['Pending'])['capabilities']['delivery'])

    def test_bookings_and_daily_capacity_validation(self):
        values=dict(Appointment_ID=['A1','A1','A2'],Appointment_Start=['2026-01-05 09:00','2026-01-05 09:00','2026-01-05 10:00'],Employee_Name=['Ana']*3,Appointment_Minutes=[30,30,60],Available_Minutes=[480]*3)
        result=self.normalized(**values)
        self.assertTrue(result['capabilities']['bookings'])
        self.assertTrue(result['capabilities']['utilization'])
        self.assertEqual(result['rows'][0]['Appointment_Hour'],9)
        values['Available_Minutes']=[480,420,480]
        self.assertFalse(self.normalized(**values)['capabilities']['utilization'])
        values['Appointment_Minutes']=[30,45,60]
        self.assertFalse(self.normalized(**values)['capabilities']['bookings'])

    def test_turnaround_excludes_unfinished_and_reversed_jobs(self):
        result=self.normalized(Job_ID=['J1','J2','J3'],Job_Status=['Done','Open','Done'],Job_Opened=['2026-01-01 08:00']*3,Job_Completed=['2026-01-02 10:00','','2025-12-31 08:00'])
        self.assertTrue(result['capabilities']['turnaround'])
        self.assertTrue(result['capabilities']['jobStatus'])
        self.assertEqual([r['Turnaround_Hours'] for r in result['rows']],[26,None,None])

    def test_waste_channel_and_aliases(self):
        result=self.normalized(Waste_Cost=[4,0],Sales_Channel=['Web','Shop'])
        self.assertTrue(result['capabilities']['waste'])
        self.assertTrue(result['capabilities']['channel'])
        self.assertFalse(self.normalized(Waste_Cost=[-1])['capabilities']['waste'])
        mapping=suggest_mapping(['Service Type','Booking ID','Duration Minutes','Staff','Sales Channel'])
        self.assertEqual(mapping['Product_Name'],'Service Type')
        self.assertEqual(mapping['Appointment_ID'],'Booking ID')
        self.assertEqual(mapping['Employee_Name'],'Staff')

    def test_invalid_and_timezone_timestamps_do_not_enable_charts(self):
        for stamp in ['bad date','2026-01-05T09:00:00+02:00']:
            self.assertFalse(self.normalized(Appointment_ID=['A1'],Appointment_Start=[stamp])['capabilities']['bookings'])
