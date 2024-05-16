import os

# Used in functions below and in views.py for the download page to order the filenames 
def file_num(filename):
        if '.PDF' in filename:
             return -1 # Don't want pandas trying to read PDF when writing invoices
        if filename[1].isdigit():
            return int(filename[0:2])
        return int(filename[0])

# Used in views.py for the home page to check whether the invoices have already been written for the latest remittance advice
def latest_filenum(path):
    latest_year = max([year for year in os.listdir(path) if len(year)==4])
    dir = os.path.join(path, latest_year)
    return max([file_num(file) for file in os.listdir(dir)])

# Used in views.py, send_emails.py and invoices.py
def latest_filename(path):
    latest_year = max([year for year in os.listdir(path) if len(year)==4])
    dir = os.path.join(path, latest_year)
    return os.path.join(dir, max(os.listdir(dir), key=file_num))