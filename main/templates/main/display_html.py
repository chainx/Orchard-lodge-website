import os

from OrchardLodge.settings import MEDIA_ROOT
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'OrchardLodge.settings')

import django
django.setup()

import mammoth


def convert_to_html(input_filename):
    with open(input_filename, "rb") as docx_file:
        result = mammoth.convert_to_html(docx_file)
        with open('output.html', 'w') as html_file:
            html_file.write(result.value)

convert_to_html(MEDIA_ROOT / 'Invoices/')