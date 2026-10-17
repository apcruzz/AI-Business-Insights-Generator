"""Revenue precedence, modifier basis, and discount regression checks."""
import unittest
import pandas as pd
from backend.normalizer import normalize, suggest_mapping


class RevenueTests(unittest.TestCase):
    def calculate(self, values, **options):
        frame = pd.DataFrame(values)
        return normalize(frame, {key:key for key in values}, 'Cafe', **options)

    def test_line_and_unit_modifiers(self):
        values = {'Quantity':[2], 'Unit_Price':[5], 'Modifier_Amount':[3], 'Discount_Amount':[1]}
        for basis, gross, net in [('line',13,12), ('unit',16,15)]:
            row = self.calculate(values, modifier_basis=basis)['rows'][0]
            self.assertEqual(row['Gross_Sales'],gross)
            self.assertEqual(row['Net_Sales'],net)

    def test_completed_line_total_never_adds_modifiers_twice(self):
        values = {'Quantity':[2], 'Unit_Price':[5], 'Modifier_Amount':[3], 'Line_Total':[13], 'Discount_Amount':[1]}
        self.assertEqual(self.calculate(values,line_total_basis='gross')['rows'][0]['Net_Sales'],12)
        self.assertEqual(self.calculate(values,line_total_basis='net')['rows'][0]['Net_Sales'],13)

    def test_authoritative_net_total_ignores_incomplete_base_price(self):
        row = self.calculate({'Quantity':[2], 'Unit_Price':[5], 'Net_Sales':[15], 'Discount_Amount':[1]})['rows'][0]
        self.assertEqual(row['Net_Sales'],15)
        self.assertEqual(row['Gross_Sales'],16)

    def test_total_only_and_profit(self):
        row=self.calculate({'Line_Total':[13], 'Total_COGS':[4]},line_total_basis='net')['rows'][0]
        self.assertEqual(row['Net_Sales'],13)
        self.assertEqual(row['Gross_Profit'],9)
        self.assertNotIn('Gross_Sales',row)

    def test_blank_modifiers_and_numeric_validation(self):
        rows=self.calculate({'Quantity':[1,1,1], 'Unit_Price':[5,5,5], 'Modifier_Amount':[None,'','  ']})['rows']
        self.assertEqual([r['Net_Sales'] for r in rows],[5,5,5])
        with self.assertRaisesRegex(ValueError,'nonnumeric'):
            self.calculate({'Quantity':[1], 'Unit_Price':[5], 'Modifier_Amount':['extra milk']})

    def test_mapping_and_ambiguous_settings(self):
        mapping=suggest_mapping(['Line Total','Modifier Price'])
        self.assertEqual(mapping['Line_Total'],'Line Total')
        self.assertEqual(mapping['Modifier_Amount'],'Modifier Price')
        self.assertEqual(suggest_mapping(['Modifiers'])['Modifier_Amount'],'')
        with self.assertRaisesRegex(ValueError,'before or after'):
            self.calculate({'Line_Total':[13]})
        with self.assertRaisesRegex(ValueError,'per sales line'):
            self.calculate({'Net_Sales':[13], 'Modifier_Amount':[3]},modifier_basis='invalid')

    def test_conflicting_totals_rejected(self):
        with self.assertRaisesRegex(ValueError,'Line total does not match'):
            self.calculate({'Line_Total':[13],'Net_Sales':[12]},line_total_basis='net')
        with self.assertRaisesRegex(ValueError,'minus discounts'):
            self.calculate({'Gross_Sales':[13],'Discount_Amount':[1],'Net_Sales':[11]})

    def test_decimal_format_and_returns(self):
        row=self.calculate({'Quantity':[-2], 'Unit_Price':['5,50'], 'Modifier_Amount':['1,50']},modifier_basis='unit',decimal='comma')['rows'][0]
        self.assertEqual(row['Net_Sales'],-14)
