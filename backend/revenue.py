"""Resolve sales amounts without adding modifiers to already-computed totals."""


def resolve_revenue(result, warnings, line_total_basis=None, modifier_basis="line"):
    """Mutate normalized numeric columns; supplied totals take priority over components."""
    if "Modifier_Amount" in result and modifier_basis not in {"line", "unit"}:
        raise ValueError("Choose whether modifier charges apply per sales line or per unit.")
    if "Modifier_Amount" in result:
        warnings.append(f"Modifier_Amount is a charge per {modifier_basis}; blank charges are treated as zero.")
    if "Line_Total" in result:
        if line_total_basis not in {"gross", "net"}:
            raise ValueError("Confirm whether Line total is before or after discounts.")
        target = "Gross_Sales" if line_total_basis == "gross" else "Net_Sales"
        # Both columns claim the same meaning: conflicting values must be corrected.
        if target in result and ((result[target] - result["Line_Total"]).abs() > .011).any():
            raise ValueError(f"Line total does not match {target}. Check its discount basis and mapping.")
        result.loc[:, target] = result["Line_Total"]
        warnings.append(f"Line total is {line_total_basis} (gross = before discounts; net = after discounts). It is used as supplied and must include add-ons, exclude tax/tips, and represent each sales line only once.")
    supplied_total = "Gross_Sales" in result or "Net_Sales" in result
    if supplied_total and "Modifier_Amount" in result:
        warnings.append("Supplied sales totals take priority. Modifier charges are retained for analysis but are not added again; confirm totals already include them.")
    # A net total is authoritative too. Derive gross only from known discounts,
    # never from base prices that may omit add-ons included in the net total.
    if "Gross_Sales" not in result and "Net_Sales" in result and "Discount_Amount" in result:
        result.loc[:, "Gross_Sales"] = (result["Net_Sales"] + result["Discount_Amount"]).round(2)
    if not supplied_total and {"Unit_Price", "Quantity"} <= set(result):
        modifiers = result.get("Modifier_Amount", 0)
        if modifier_basis == "unit":
            modifiers = modifiers * result["Quantity"]
        result.loc[:, "Gross_Sales"] = (result["Quantity"] * result["Unit_Price"] + modifiers).round(2)
        if "Modifier_Amount" in result:
            warnings.append(f"Gross sales includes modifier charges per {modifier_basis}; unit price must exclude these charges.")
    if "Net_Sales" not in result:
        if "Gross_Sales" not in result:
            raise ValueError("Map net sales, gross sales, line total, or both quantity and unit price.")
        result.loc[:, "Net_Sales"] = (result["Gross_Sales"] - result.get("Discount_Amount", 0)).round(2)
        if "Discount_Amount" not in result:
            warnings.append("No discounts column was provided: net sales is treated as gross sales. Returns and tax treatment depend on your source.")
    if {"Gross_Sales", "Discount_Amount"} <= set(result) and ((result["Gross_Sales"] - result["Discount_Amount"] - result["Net_Sales"]).abs() > .011).any():
        raise ValueError("Gross sales minus discounts does not match net sales. Confirm that discounts are line amounts, and revenue excludes tax and tips.")
