# Mapping vocabulary shared by column suggestions and normalization; keys match frontend field IDs.
"""Canonical dashboard fields and aliases used for source-column mapping."""

# Each canonical field lists simplified source headers that can be mapped automatically.
FIELDS = {
    "Date": ["date", "orderdate", "saledate", "transactiondate", "datetime", "timestamp"],
    "Time": ["time", "ordertime", "transactiontime"],
    "Hour": ["hour", "hourofday"],
    "Product_Name": ["productname", "product", "itemname", "item", "dish", "sku"],
    "Category": ["category", "productcategory", "department"],
    "Quantity": ["quantity", "qty", "unitssold"],
    "Unit_Price": ["unitprice", "price", "sellingprice"],
    "Gross_Sales": ["grosssales", "grossrevenue"],
    "Discount_Amount": ["discountamount", "discounts", "discountvalue"],
    "Net_Sales": ["netsales", "netrevenue", "salesrevenue", "revenue"],
    "Unit_COGS": ["unitcogs", "unitcost", "costperunit"],
    "Total_COGS": ["totalcogs", "cogs", "totalcost", "costofgoodssold"],
    "Gross_Profit": ["grossprofit"],
    "Transaction_ID": ["transactionid", "orderid", "receiptid", "invoicenumber", "invoiceid"],
    "Employee_Name": ["employeename", "employee", "cashier", "salesperson", "server"],
    "Payment_Method": ["paymentmethod", "paymenttype"],
    "Weather": ["weather", "weathersignal"],
    "Store_Location": ["storelocation", "store", "location"],
}
