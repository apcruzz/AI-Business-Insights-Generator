"""Validate optional operational data without inventing missing business metrics.

Sales normalization stays in normalizer.py. This module adds canonical fields and
capabilities for the chart registry; invalid event groupings disable only those charts.
"""
from datetime import datetime

BUSINESS_FIELDS = {
    "Sales_Channel": ["saleschannel", "channel", "orderchannel"],
    "Waste_Cost": ["wastecost", "wastagecost", "spoilagecost"],
    "Delivery_ID": ["deliveryid", "shipmentid"],
    "Delivery_Status": ["deliverystatus", "deliveryperformance"],
    "Delivery_Due": ["deliverydue", "promiseddeliverydate", "expecteddeliverydate"],
    "Delivered_At": ["deliveredat", "actualdeliverydate", "deliverydate"],
    "Appointment_ID": ["appointmentid", "bookingid"],
    "Appointment_Start": ["appointmentstart", "appointmentdatetime", "bookingdatetime"],
    "Appointment_Status": ["appointmentstatus", "bookingstatus"],
    "Appointment_Minutes": ["appointmentminutes", "durationminutes", "bookedminutes"],
    "Available_Minutes": ["availableminutes", "staffavailableminutes", "shiftminutes"],
    "Job_ID": ["jobid", "repairid", "workorderid"],
    "Job_Status": ["jobstatus", "repairstatus"],
    "Job_Opened": ["jobopened", "jobopenedat", "receivedat"],
    "Job_Completed": ["jobcompleted", "jobcompletedat", "completedat"],
}
NUMERIC_FIELDS = {"Waste_Cost", "Appointment_Minutes", "Available_Minutes"}
DATE_FIELDS = {"Delivery_Due", "Delivered_At", "Appointment_Start", "Job_Opened", "Job_Completed"}


def enrich_business_data(result, mapped, parse_date, dayfirst, warnings):
    """Derive operational values, checking repeated IDs before enabling charts."""
    caps = {}
    for field in DATE_FIELDS & set(mapped):
        parsed = [parse_date(v, dayfirst) if str(v).strip() else None for v in result[field]]
        # Use ISO timestamps throughout; mixed timezone offsets are not interpreted as local shifts.
        valid = all(v is None or v.utcoffset() is None for v in parsed)
        if not valid:
            warnings.append(f"{field} must use consistent local timestamps without timezone offsets; related charts are unavailable.")
            parsed = [None] * len(result)
        result[field] = [v.isoformat() if v else None for v in parsed]
        if any(v is None for v in parsed):
            warnings.append(f"Blank or invalid {field} values are excluded from related operational calculations.")

    def present(field):
        return field in mapped and result[field].notna().all() and result[field].astype(str).str.strip().ne("").all()

    def events_valid(id_field, fields):
        # A delivery, booking, or job can occupy multiple sales lines; count its ID once.
        if not present(id_field) or not all(f in result for f in fields):
            return False
        groups = result.groupby(id_field)
        if any((groups[f].nunique(dropna=False) > 1).any() for f in fields):
            warnings.append(f"Repeated {id_field} values have conflicting details; related event charts are unavailable.")
            return False
        return True

    caps['channel'] = present('Sales_Channel')
    caps['waste'] = 'Waste_Cost' in mapped and present('Product_Name') and (result['Waste_Cost'] >= 0).all()
    if 'Waste_Cost' in mapped:
        warnings.append("Waste cost is summed per source row. Map line-level waste amounts, not a daily total repeated across sales lines.")
        if not caps['waste']:
            warnings.append("Waste charts require product names and nonnegative waste costs.")

    if 'Delivery_Status' in mapped:
        labels = result['Delivery_Status'].str.lower().str.strip().str.replace(r'[-_]', ' ', regex=True)
        result['Delivery_Outcome'] = labels.map({'on time':'On time', 'ontime':'On time', 'early':'On time', 'late':'Late'})
    elif {'Delivery_Due', 'Delivered_At'} <= set(mapped):
        result['Delivery_Outcome'] = [
            ('On time' if delivered <= due else 'Late') if due and delivered else None
            for due, delivered in zip(result['Delivery_Due'], result['Delivered_At'])]
    caps['delivery'] = events_valid('Delivery_ID', ['Delivery_Outcome']) and result['Delivery_Outcome'].notna().any()
    if caps['delivery']:
        warnings.append("Delivery charts count each delivery ID once. Pending, blank, or unrecognized outcomes are excluded; delivery timestamps should use the same precision.")

    if 'Appointment_Start' in result:
        result['Appointment_Day'] = result['Appointment_Start'].map(lambda v: v[:10] if v else None)
        result['Appointment_Hour'] = result['Appointment_Start'].map(lambda v: int(v[11:13]) if v else None)
    booking_fields = ['Appointment_Start'] + [f for f in ('Employee_Name', 'Appointment_Status', 'Appointment_Minutes') if f in mapped]
    caps['bookings'] = events_valid('Appointment_ID', booking_fields) and result['Appointment_Start'].notna().any()
    caps['utilization'] = False
    if caps['bookings'] and all(present(f) for f in ('Employee_Name', 'Appointment_Minutes', 'Available_Minutes', 'Appointment_Start')):
        capacity = result.groupby(['Employee_Name', 'Appointment_Day'])['Available_Minutes']
        caps['utilization'] = bool((result['Appointment_Minutes'] >= 0).all() and (result['Available_Minutes'] > 0).all() and (capacity.nunique() == 1).all())
        if not caps['utilization']:
            warnings.append("Utilization needs nonnegative appointment minutes and one consistent positive available-minutes value per staff member per day.")
    if caps['bookings']:
        warnings.append("Bookings count appointment IDs once, excluding cancelled/canceled/no-show appointments. Utilization is booked minutes divided by supplied daily availability for represented staff-days; it is not measured working time.")

    caps['jobStatus'] = events_valid('Job_ID', ['Job_Status']) and present('Job_Status')
    if {'Job_Opened', 'Job_Completed'} <= set(mapped):
        durations = []
        for opened, completed in zip(result['Job_Opened'], result['Job_Completed']):
            hours = (datetime.fromisoformat(completed) - datetime.fromisoformat(opened)).total_seconds() / 3600 if opened and completed else None
            durations.append(hours if hours is not None and hours >= 0 else None)
        result['Turnaround_Hours'] = durations
        caps['turnaround'] = events_valid('Job_ID', ['Product_Name', 'Job_Opened', 'Job_Completed']) and present('Product_Name') and result['Turnaround_Hours'].notna().any()
        warnings.append("Turnaround averages completed jobs once per job ID in elapsed hours; missing or reversed timestamps are excluded.")
    else:
        caps['turnaround'] = False
    return {key: bool(value) for key, value in caps.items()}
