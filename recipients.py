"""Single place for who the scheduled tasks (notify.py, backup.py,
weekview.py) email/text. Previously this list was hardcoded separately in
each of those three files and had drifted out of sync between them -
update it here instead of hunting through three files.
"""

# (email, LeadConnector/Genie contact id) - office staff who get the
# day-before job sheet email + SMS the same as crew (notify.py), and the
# daily backup email (backup.py).
OFFICE = [
    ("john@chorleyconcrete.co.uk", "jYZ3fvCEBeXZl2sOslWv"),
    ("tommy@chorleyconcrete.co.uk", "aVCQaF4pXtzZ0VLpbyj3"),
]

BACKUP_TO = [email for email, _ in OFFICE]

# Who gets the Monday "what's free" diary email. This has historically
# included james@chorleyconcrete.co.uk, who is NOT in OFFICE above and so
# doesn't get the day-before job notifications or the daily backup - worth
# confirming that split is actually intentional.
WEEKVIEW_TO = BACKUP_TO + ["james@chorleyconcrete.co.uk"]
