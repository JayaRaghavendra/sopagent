from pathlib import Path
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

base = Path(r"c:\Users\e430107\Downloads\SOP_Agent")
metrics_path = base / "metrics.xlsx"

# Create mock data: proper datetime in a 'date' column, 'metric', 'category', 'value'
start = datetime(2025, 1, 1)
rows = []
metrics = [
    ("csr_supply", "CSR"),
    ("spend", "FINANCE"),
]
for i in range(180):  # ~6 months of daily data
    dt = start + timedelta(days=i)
    for m, cat in metrics:
        # simple synthetic values
        val = 50 + (i % 30) * 10 if m == "csr_supply" else 100 + (i % 7) * 25
        rows.append({"date": dt, "metric": m, "category": cat, "value": float(val)})

pd.DataFrame(rows).to_excel(metrics_path, index=False)
print("Wrote", metrics_path)

# Append new checks to checks.xlsx
checks_path = base / "checks.xlsx"
df = pd.read_excel(checks_path)
extra_checks = [
    {"Check": "Aggregate monthly data for March 2025 should be less than 1200", "Email": "", "Status": "", "Explanation": ""},
    {"Check": "CSR supply in April 2025 equals 450", "Email": "", "Status": "", "Explanation": ""},
    {"Check": "Total for 2025-03 must be >= 1000", "Email": "", "Status": "", "Explanation": ""},
    {"Check": "Spend on this item was this week 932 dollars", "Email": "", "Status": "", "Explanation": ""},
]

pd.concat([df, pd.DataFrame(extra_checks)], ignore_index=True).to_excel(checks_path, index=False)
print("Appended extra checks to", checks_path)
