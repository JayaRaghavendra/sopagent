from pathlib import Path
import pandas as pd

base = Path(r"c:\Users\e430107\Downloads\SOP_Agent")

# Contacts data from screenshot
contacts = [
    {"id": 1, "name": "Alex Sample", "email": "alex.sample@novartis.com", "role": "Engineer"},
    {"id": 2, "name": "Bailey", "email": "bailey@gmail.com", "role": "Analyst"},
    {"id": 3, "name": "Casey Placeholder", "email": "casey.placeholder@yahoo.org", "role": "Manager"},
    {"id": 4, "name": "Dana Mock", "email": "dana.mock@theboringcompany.org", "role": "Designer"},
    {"id": 5, "name": "Evan Dummy", "email": "evan.dummy@starlink.com", "role": "Research"},
    {"id": 6, "name": "Frankie Faux", "email": "frankie.faux@gmail.com", "role": "Product"},
    {"id": 7, "name": "Gale Testuser", "email": "gale.testuser@gramener.org", "role": "Support"},
    {"id": 8, "name": "Harper Sampleton", "email": "harper.sampleton@straive.com", "role": "Sales"},
    {"id": 9, "name": "Ira Placeholder", "email": "ira.placeholder@microsoft.com", "role": "HR"},
]

pd.DataFrame(contacts).to_excel(base / "contacts.xlsx", index=False)

# Checks from screenshot, adding email in one of the rows
checks = [
    {"Check": "Perform domain check for new email address", "Email": "new.person@novartis.com", "Status": "", "Explanation": ""},
    {"Check": "Confirm domain not blacklisted", "Email": "", "Status": "", "Explanation": ""},
    {"Check": "Perform domain check only when new email discovered", "Email": "new.alias@gmail.com", "Status": "", "Explanation": ""},
    {"Check": "Skip domain check if no new info introduced", "Email": "", "Status": "", "Explanation": ""},
]

pd.DataFrame(checks).to_excel(base / "checks.xlsx", index=False)
print("Wrote contacts.xlsx and checks.xlsx")
