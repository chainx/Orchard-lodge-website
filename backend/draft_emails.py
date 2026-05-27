import imaplib
import json
import os
import sys
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import django
django.setup()
from django.conf import settings

from backend.file_utils import latest_invoice_batch, invoice_path, invoice_period

GMAIL_IMAP_SERVER = 'imap.gmail.com'
GMAIL_DRAFT_MAILBOX = '[Gmail]/Drafts'

SUBJECT_TEMPLATE = 'Invoice {invoice_number} from Orchard Lodge'
MESSAGE_TEMPLATE = """Dear {email_name},

Please find attached invoice {invoice_number} totaling {invoice_total} for care of {resident_name} at Orchard Lodge care home from {start_date} to {end_date}.

Kind regards,
Michael Kiss
Finance - Orchard Lodge
"""

def draft_emails():
    email_details = json.load(open(settings.SECRET_MEDIA_ROOT / 'Email_details.json'))
    invoices = latest_invoice_batch()
    skipped, drafted = [], []
    try:
        with imaplib.IMAP4_SSL(GMAIL_IMAP_SERVER) as imap:
            imap.login(email_details["EMAIL_ADDRESS"], email_details["EMAIL_PASSWORD"])

            for invoice_ in invoices:
                resident = invoice_.Resident
                if not resident.email:
                    skipped.append(resident.name)
                    continue

                msg = build_invoice_email(invoice_, email_details)
                mailbox = append_to_gmail_drafts(imap, msg)
                drafted.append((resident.name, resident.email, mailbox))
    except imaplib.IMAP4.error as exc:
        raise RuntimeError(
            'Could not log in to Gmail. Check that IMAP is enabled.'
        ) from exc

    for resident_name, recipient, mailbox in drafted:
        print(f'Draft saved in {mailbox} for {resident_name} <{recipient}>')

    if skipped:
        print('Skipped residents with no email address: ' + ', '.join(skipped))

def message_context(invoice_):
    resident = invoice_.Resident
    start_date, end_date = invoice_period(invoice_)
    return {
        'email_name': resident.email_name or resident.name,
        'resident_name': resident.name,
        'resident_first_name': resident.first,
        'resident_last_name': resident.last,
        'customer_ref_no': resident.customer_ref_no or '',
        'invoice_number': invoice_.invoice_number,
        'invoice_total': invoice_.str_total,
        'invoice_date': invoice_.date.strftime('%d %B %Y'),
        'start_date': start_date,
        'end_date': end_date,
    }


def build_invoice_email(invoice_, email_details):
    resident = invoice_.Resident
    context = message_context(invoice_)
    path = invoice_path(invoice_)

    msg = MIMEMultipart()
    msg.attach(MIMEText(MESSAGE_TEMPLATE.format(**context), 'plain'))
    msg['From'] = email_details["EMAIL_ADDRESS"]
    msg['To'] = resident.email
    msg['Cc'] = email_details['CC']
    msg['Bcc'] = email_details['BCC']
    msg['Subject'] = SUBJECT_TEMPLATE.format(**context)

    with open(path, 'rb') as attachment:
        obj = MIMEApplication(attachment.read(), _subtype='docx')
    obj.add_header('Content-Disposition', 'attachment', filename=os.path.basename(path))
    msg.attach(obj)

    return msg

def append_to_gmail_drafts(imap, msg):
    encoded_message = msg.as_bytes()

    status, response = imap.append(GMAIL_DRAFT_MAILBOX, '\\Draft', None, encoded_message)
    if status == 'OK':
        return GMAIL_DRAFT_MAILBOX

    raise RuntimeError(f'Could not save message to Gmail Drafts folder: {response}')

if __name__ == '__main__':
    draft_emails()
