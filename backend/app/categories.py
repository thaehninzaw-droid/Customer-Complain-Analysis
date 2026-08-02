"""
The single source of truth for the category list.

Before this file existed, "the 5 categories" were hardcoded in three
different places (two HTML forms and the classifier) and had already
drifted out of sync with each other. Whichever piece of code needs
the category list - the classifier, the chatbot templates, or the
new GET /categories endpoint - should import it from here. Nowhere
else should type out the list by hand again.

This is provisional (matches activities.html's dropdown) until the
team confirms it for real - see DECISIONS.md. When it changes, it
only needs to change in this one file.
"""

CATEGORIES = ["Billing", "Financial", "Technical", "Service", "Others"]
