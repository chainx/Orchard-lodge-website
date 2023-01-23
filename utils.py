import os

def file_num(file):
        if file[1].isdigit():
            return int(file[0:2])
        return int(file[0])

def get_latest(path):
    latest_year = max([year for year in os.listdir('Invoices') if len(year)==4])
    dir = path + '/' + latest_year
    return dir + '/' + max(os.listdir(dir), key=file_num)

def latest_num(path):
    latest_year = max([year for year in os.listdir('Invoices') if len(year)==4])
    dir = path + '/' + latest_year
    return max([file_num(file) for file in os.listdir(dir)])