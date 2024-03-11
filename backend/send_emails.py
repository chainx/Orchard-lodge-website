import smtplib
import ssl
import email
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.text import MIMEText

import os
import json

from django.conf import settings
from backend.utils import get_latest

SERVER_ADDRESS, SERVER_PORT = 'smtp-mail.outlook.com', 587

def send_email():
    path = get_latest(settings.MEDIA_INVOICES)
    Email_details = json.load(open(os.path.join(settings.MEDIA_ROOT, 'Email_details.json')))
    
    msg = MIMEMultipart()
    msg.attach(MIMEText(Email_details['MESSAGE']))
    msg['From'] = Email_details['EMAIL_ADDRESS']
    msg['To'] = Email_details['RECIPIENT_EMAIL']
    msg['Cc'] = ', '.join(Email_details['CC'])
    msg['Subject'] = "Invoices for Orchard lodge"

    for file in os.listdir(path):
        with open(path+file,'rb') as attachment:
            obj = MIMEApplication(attachment.read(), _subtype = "docx")
        obj.add_header('Content-Disposition',"attachment",filename=file)
        msg.attach(obj)

    with smtplib.SMTP(SERVER_ADDRESS, SERVER_PORT) as smtp:
        context = ssl.create_default_context()
        smtp.starttls(context=context)
        smtp.login(Email_details['EMAIL_ADDRESS'], Email_details['EMAIL_PASSWORD'])
        smtp.sendmail(Email_details['EMAIL_ADDRESS'], Email_details['RECIPIENT_EMAIL'], msg.as_string())

if __name__=='__main__':
    send_email()
