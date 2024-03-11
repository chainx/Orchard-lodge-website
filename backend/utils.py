import os

def get_latest(path):
    latest_year = max([year for year in os.listdir(path) if len(year)==4])
    dir = os.path.join(path, latest_year)
    return dir + '/' + max(os.listdir(dir), key=file_num)

def file_num(filename):
        if '.PDF' in filename:
             return -1 # Don't want pandas trying to read PDF when writing invoices
        if filename[1].isdigit():
            return int(filename[0:2])
        return int(filename[0])

def latest_num(path):
    latest_year = max([year for year in os.listdir(path) if len(year)==4])
    dir = os.path.join(path, latest_year)
    return max([file_num(file) for file in os.listdir(dir)])