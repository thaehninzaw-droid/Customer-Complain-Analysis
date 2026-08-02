"""
Generates a SYNTHETIC complaint dataset shaped exactly like the real
Kaggle "Comcast Telecom Complaints" CSV (same column names), so the
existing `data/load_dataset.py` loader and the ML training scripts in
`app/ml/` can be developed and tested end-to-end in an environment
with no internet access to actually download the real dataset.

*** THIS IS NOT REAL DATA. *** It is templated text with randomized
slot-filling (city/state/date/severity wording), generated so there's
enough vocabulary variety for TF-IDF and enough sentiment/urgency
range for the priority model to learn something real from. Swap in
the real Kaggle CSV (yasserh/comcast-telecom-complaints) the moment
someone on the team has internet access - no code changes needed
anywhere else, since the schema matches exactly. See
docs/ALGORITHMS.md and DECISIONS.md for the full explanation of why
this exists and how to replace it.

Usage:
    python -m data.generate_synthetic_dataset [n_rows] [output_path]
    (defaults: 600 rows -> data/synthetic_complaints.csv)
"""
import csv
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)  # reproducible dataset across runs

CITIES = [
    ("Springfield", "IL", "62701"), ("Austin", "TX", "73301"),
    ("Denver", "CO", "80014"), ("Miami", "FL", "33101"),
    ("Seattle", "WA", "98101"), ("Atlanta", "GA", "30301"),
    ("Chicago", "IL", "60601"), ("Phoenix", "AZ", "85001"),
    ("Boston", "MA", "02101"), ("Portland", "OR", "97201"),
    ("Nashville", "TN", "37201"), ("Dallas", "TX", "75201"),
    ("San Diego", "CA", "92101"), ("Columbus", "OH", "43085"),
    ("Baltimore", "MD", "21201"),
]

RECEIVED_VIA = ["Internet", "Customer Care Call"]

DURATIONS = ["two days", "three days", "a week", "two weeks", "three weeks", "a month", "several months"]
AMOUNTS = ["$15", "$22.50", "$40", "$65", "$89.99", "$120", "$210"]

# ---------------------------------------------------------------------------
# Template bank: (category, severity, template_string)
# severity is only used to bias which modifier phrases get appended - the
# actual priority pseudo-label is computed later from the FINAL text via
# app/sentiment.py + app/priority.py, never hardcoded here. That keeps the
# labeling honest (distant supervision from a documented heuristic, not
# labels baked in by the generator).
# ---------------------------------------------------------------------------

TEMPLATES = [
    # ---- Billing ----
    ("Billing", "mild", "I have a question about a charge of {amount} on my latest bill, could someone clarify it?"),
    ("Billing", "mild", "My monthly bill seems higher than usual this cycle, can you check the breakdown?"),
    ("Billing", "moderate", "I was charged {amount} twice on my bill this month and would like it corrected."),
    ("Billing", "moderate", "My bill shows a late fee even though I paid on time, please review my account."),
    ("Billing", "severe", "I have been overcharged {amount} for {duration} now and no one has fixed my billing statement."),
    ("Billing", "severe", "This is the second month in a row my bill is wrong by {amount} and support keeps ignoring my emails."),
    ("Billing", "severe", "I was billed for a package I never signed up for and it has taken {duration} to even get a reply."),

    # ---- Financial ----
    ("Financial", "mild", "I would like to ask about the refund process for a canceled service."),
    ("Financial", "mild", "Can someone confirm when my deposit will be returned after I closed my account?"),
    ("Financial", "moderate", "I requested a refund of {amount} {duration} ago and have not received it yet."),
    ("Financial", "moderate", "The promotional credit of {amount} was never applied to my account as promised."),
    ("Financial", "severe", "I cancelled my service {duration} ago and my {amount} deposit still has not been refunded."),
    ("Financial", "severe", "Nobody will process my {amount} refund even though I have called {duration} in a row about it."),

    # ---- Technical ----
    ("Technical", "mild", "My internet speed seems a little slower than what I'm paying for, could you check the line?"),
    ("Technical", "mild", "I'd like a technician to take a look at my router configuration when convenient."),
    ("Technical", "moderate", "My internet connection keeps disconnecting every few minutes since yesterday."),
    ("Technical", "moderate", "My modem stopped working and I still don't have a working connection."),
    ("Technical", "severe", "My internet has been completely down for {duration} and no technician has shown up yet."),
    ("Technical", "severe", "This is the third technician appointment that has been missed and I still have no service."),
    ("Technical", "severe", "My connection drops every hour and I work from home, I cannot keep losing income like this."),

    # ---- Service ----
    ("Service", "mild", "I had a fine experience overall but wanted to mention the hold time was a bit long."),
    ("Service", "mild", "Just leaving feedback that the chat support could be a little faster to respond."),
    ("Service", "moderate", "The representative I spoke to was short with me and didn't answer my question."),
    ("Service", "moderate", "I have been on hold for over an hour trying to reach customer support."),
    ("Service", "severe", "The agent was extremely rude to me on the phone and hung up before resolving my issue."),
    ("Service", "severe", "I have called {duration} in a row and every representative gives me a different answer with no resolution."),
    ("Service", "severe", "Nobody has followed up with me after promising a callback {duration} ago, this is unacceptable."),

    # ---- Others ----
    ("Others", "mild", "I have a general question about upgrading my current plan."),
    ("Others", "mild", "Could you send me information about available add-on packages?"),
    ("Others", "moderate", "I want to cancel my subscription but keep getting transferred between departments."),
    ("Others", "moderate", "I moved recently and need to update my service address, but the website won't let me."),
    ("Others", "severe", "I have tried to cancel my account for {duration} and keep getting transferred with no resolution."),
    ("Others", "severe", "Nobody can tell me why my account was suspended without any notice {duration} ago."),
]

# Extra sentences randomly appended to increase lexical diversity and
# occasionally shift sentiment/urgency independently of the base template
# (so the priority label isn't perfectly correlated with the category
# template alone - a calm Billing complaint can still end up High priority
# if enough escalation language gets appended, and vice versa).
MODIFIER_POOL = [
    "",
    "",
    " Please let me know as soon as possible.",
    " This is not urgent, just wanted to flag it.",
    " I would appreciate a quick response.",
    " I am extremely frustrated at this point.",
    " I am considering switching providers over this.",
    " Thank you for looking into this.",
    " I have been a loyal customer for years and expected better.",
    " Please escalate this to a supervisor if needed.",
    " This has happened before and I don't want it to happen again.",
    " I need this resolved immediately, I cannot wait any longer!",
    " No rush on this, whenever you get a chance is fine.",
    " I've already called twice about this exact issue.",
]

STATUSES = ["Open", "Pending", "Closed", "Solved"]

# Weighted so the dataset isn't overwhelmingly mild/moderate - real
# complaint queues skew that way too, but a near-empty "High" class
# makes it hard to train or evaluate that class meaningfully. This is
# a generator-tuning choice, not a claim about real-world proportions.
SEVERITY_WEIGHT = {"mild": 1.0, "moderate": 1.4, "severe": 1.8}


def _fill(template: str) -> str:
    return template.format(
        amount=random.choice(AMOUNTS),
        duration=random.choice(DURATIONS),
    )


def _weighted_template_choice():
    weights = [SEVERITY_WEIGHT[t[1]] for t in TEMPLATES]
    return random.choices(TEMPLATES, weights=weights, k=1)[0]


def generate_rows(n: int):
    start_date = datetime(2025, 1, 1)
    rows = []
    for i in range(1, n + 1):
        category, severity, template = _weighted_template_choice()
        text = _fill(template)
        modifier = random.choice(MODIFIER_POOL)
        text = (text + modifier).strip()

        city, state, zipc = random.choice(CITIES)
        date = start_date + timedelta(days=random.randint(0, 545))
        rows.append({
            "Ticket #": i,
            "Customer Complaint": text,
            "Date": date.strftime("%Y-%m-%d"),
            "Date_month_year": date.strftime("%b-%y"),
            "Time": f"{random.randint(0,23):02d}:{random.randint(0,59):02d}",
            "Received Via": random.choice(RECEIVED_VIA),
            "City": city,
            "State": state,
            "Zip code": zipc,
            "Status": random.choice(STATUSES),
            "Filing on Behalf of Someone": random.choice(["Yes", "No", "No", "No"]),
            # Not part of the real Kaggle schema - kept ONLY so train_classifier.py
            # can report accuracy against something while developing. The real
            # pipeline never trusts this column; it exists purely for this
            # synthetic generator's own evaluation convenience and is dropped
            # by data/load_dataset.py (which only reads the Kaggle columns).
            "_template_category": category,
        })
    return rows


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 600
    out_path = sys.argv[2] if len(sys.argv) > 2 else str(Path(__file__).parent / "synthetic_complaints.csv")

    rows = generate_rows(n)
    fieldnames = [
        "Ticket #", "Customer Complaint", "Date", "Date_month_year", "Time",
        "Received Via", "City", "State", "Zip code", "Status",
        "Filing on Behalf of Someone", "_template_category",
    ]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} synthetic complaints to {out_path}")


if __name__ == "__main__":
    main()
