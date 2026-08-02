"""
Ticket numbering - matches the scheme already used client-side in
script.js's generateNextTicketNo(): starts at 100001, and each new
complaint gets (current max ticket_no) + 1.
"""


def next_ticket_no(existing_ticket_nos) -> int:
    return max(existing_ticket_nos, default=100000) + 1
