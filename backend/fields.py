# Mapping vocabulary shared by column suggestions and normalization; keys match frontend field IDs.
"""Canonical dashboard fields and aliases used for source-column mapping."""

# Each canonical field lists simplified source headers that can be mapped automatically.
from backend.business_data import BUSINESS_FIELDS

FIELDS = {
    "Date": ["date", "orderdate", "saledate", "transactiondate", "datetime", "timestamp"],
    "Time": ["time", "ordertime", "transactiontime"],
    "Hour": ["hour", "hourofday"],
    "Product_Name": ["productname", "product", "itemname", "item", "dish", "sku", "service", "servicename", "servicetype", "repairtype"],
    "Category": ["category", "productcategory", "department"],
    "Quantity": ["quantity", "qty", "unitssold"],
    "Unit_Price": ["unitprice", "price", "sellingprice"],
    "Modifier_Amount": ["modifieramount", "modifiertotal", "modifierprice", "modifiercharge", "addonamount", "addontotal", "addonprice", "addoncharge", "extrasamount"],
    "Line_Total": ["linetotal", "lineamount", "itemtotal", "extendedprice"],
    "Gross_Sales": ["grosssales", "grossrevenue"],
    "Discount_Amount": ["discountamount", "discounts", "discountvalue"],
    "Net_Sales": ["netsales", "netrevenue", "salesrevenue", "revenue"],
    "Unit_COGS": ["unitcogs", "unitcost", "costperunit"],
    "Total_COGS": ["totalcogs", "cogs", "totalcost", "costofgoodssold"],
    "Gross_Profit": ["grossprofit"],
    "Transaction_ID": ["transactionid", "orderid", "receiptid", "invoicenumber", "invoiceid"],
    "Employee_Name": ["employeename", "employee", "cashier", "salesperson", "server", "staff", "staffname", "stylist", "technician"],
    "Payment_Method": ["paymentmethod", "paymenttype"],
    "Weather": ["weather", "weathersignal"],
    "Store_Location": ["storelocation", "store", "location"],
}

# Optional delivery, booking, waste, channel, and repair-job dimensions.
FIELDS.update(BUSINESS_FIELDS)
