"""
The single source of truth for the category list.

Before this file existed, "the 5 categories" were hardcoded in three
different places (two HTML forms and the classifier) and had already
drifted out of sync with each other. Whichever piece of code needs
the category list - the classifier, the chatbot templates, or the
new GET /categories endpoint - should import it from here. Nowhere
else should type out the list by hand again.

Decision 34: pivoted from telecom to banking categories (advisor
request, August 2026). Mapped from CFPB Consumer Complaint Database
Product field. See backend/data/EDA.md for the full mapping table
and backend/data/clean_banking_dataset.py for the cleaning pipeline.
"""

CATEGORIES = [
    "Cards",
    "Accounts",
    "Loans",
    "Collections & Credit reporting",
    "Other banking",
]
