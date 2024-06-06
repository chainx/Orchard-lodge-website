from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options

import argparse
import os
import datetime
import time
import json

import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import django
django.setup()
from django.conf import settings

LOGIN_DETAILS = json.load(open(settings.SECRET_MEDIA_ROOT / 'Santander_login.json'))

COOKIE_DIR = LOGIN_DETAILS['SANTANDER_COOKIE_DIR']
AGENT_STRING = LOGIN_DETAILS["AGENT_STRING"]
BANK_DETAILS = LOGIN_DETAILS['BANK_DETAILS']
PID = BANK_DETAILS["PID"]
SECURITY_NUMBER = BANK_DETAILS["SECURITY_NUMBER"]

SANTANDER_LOGIN_URl = 'https://business.santander.co.uk/olb/app/logon/access/#/logon'

FILE_FORMAT_DICT = { # These file format values were obtained from the HTML of the Santander downloads page
    'Microsoft Excel (XLS)': '1',
    'Microsoft Money (QIF)': '2',
    'Intuit Quicken (QIF)': '3',
    'Adobe Acrobat (PDF)': '4',
    'Text file (TXT)': '5',
}

options = Options()
options.add_argument("user-data-dir="+COOKIE_DIR)
options.add_experimental_option("prefs", {
    "download.default_directory": os.path.join(settings.MEDIA_PAYMENTS, 'Santander')
})

def main():
    parser = argparse.ArgumentParser(description='Script that accepts --headless flag and a date argument.')
    parser.add_argument('--headless', type=int, default=0, choices=[0, 1],
                        help='Flag to indicate whether to run in headless mode (0 for False, 1 for True). Default is 0.')
    parser.add_argument('date', type=str, help='Date in the format DD-MM-YYYY')
    args = parser.parse_args()
    headless = bool(args.headless)
    date = args.date.replace('/', '-')
    from_date = datetime.datetime.strptime(date, '%d-%m-%Y').date()

    scrape_santander_bank_statements(from_date, datetime.datetime.now().date(), headless)


# ======================================================================================================================


def scrape_santander_bank_statements(from_date, to_date, headless=False):
    if headless:
        options.add_argument('--headless')
        options.add_argument('--disable-gpu')
        options.add_argument("window-size=1200x600")
        options.add_argument("user-agent="+AGENT_STRING)  

    driver = webdriver.Chrome(options=options, service=Service(ChromeDriverManager().install()))
    driver.get(SANTANDER_LOGIN_URl)

    log_in(driver)
    navigate_to_download_page(driver)

    date_partition = partition_dates(from_date, to_date)
    for date_range in date_partition:
        for i in range(2):
            to_or_from = 'from' if i==0 else 'to'
            input_date_form(driver, to_or_from, date_range[i])
        download_bank_statement(driver, date_range[0], date_range[1])

    driver.quit()

def download_bank_statement(driver, from_date, to_date, file_format='Microsoft Excel (XLS)', download=True):
    try:
        file_format_element = driver.find_element(By.ID, "sel_downloadto")
        file_format_form = Select(file_format_element)
        file_format_form.select_by_value(FILE_FORMAT_DICT[file_format])
    except:
        print('File format cannot be selected')

    try:
        download_button = driver.find_element(By.NAME, "downloadStatementsForm.events.0")
        if download:
            download_button.click()
            print(f'Download for period from {from_date} to {to_date} complete!')
            time.sleep(1) # Put a better wait condition here
    except:
        print('Download failed')

# =========================================================================================================================================================


def log_in(driver):
    try:
        accept_cookies_button = WebDriverWait(driver, 1).until(
            EC.presence_of_element_located((By.ID, 'onetrust-accept-btn-handler'))
        )
        accept_cookies_button.click()
    except:
        pass

    pid_form = driver.find_element(By.ID, 'pid')
    pid_form.send_keys(PID)
    security_num_form = driver.find_element(By.ID, 'securityNumber')
    security_num_form.send_keys(SECURITY_NUMBER)

    wait = WebDriverWait(driver, 10)
    wait.until(EC.invisibility_of_element_located((By.CLASS_NAME, "onetrust-pc-dark-filter")))
    logon_button = driver.find_element(By.ID, 'submitbtn')
    logon_button.click()

    wait = WebDriverWait(driver, 10)
    wait.until(EC.url_changes(driver.current_url))
    time.sleep(5) # Wait some additional time for a further redirect

    if driver.current_url == 'https://business.santander.co.uk/olb/app/logon/access/#/otp':
        two_factor_authentication(driver)
    if driver.current_url == 'https://business.santander.co.uk/olb/app/logon/interstitial/#/': # TODO: Fix this
        not_interested(driver)
        
def navigate_to_download_page(driver):
    element = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.XPATH, "//a[text()='Orchard Lodge Current']"))
    )
    href_value = element.get_attribute("href")
    driver.get(href_value)

    element = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CLASS_NAME, 'download'))
    )
    href_value = element.get_attribute("href")
    driver.get(href_value)

def input_date_form(driver, to_or_from, date):
    day, month, year = date.strftime("%d %m %Y").split()
    input_date_form_field(driver, to_or_from, 'day', day)
    input_date_form_field(driver, to_or_from, 'month', month)
    input_date_form_field(driver, to_or_from, 'year', year)

def input_date_form_field(driver, to_or_from, day_month_year_type, day_month_year_value):
    name = f'downloadStatementsForm.{to_or_from}Date.{day_month_year_type}'
    try:
        date_form = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, name))
        )
    except:
        print('Could not get the following date form input:', name)
    
    date_form.clear()
    date_form.send_keys(day_month_year_value)

# Santander has a limit on how many transactions can be downloaded in one go, so the full time period
# must be split into 3 month components to ensure the limit is not reached
def partition_dates(from_date, to_date): 
    date_partition = [from_date]
    date = from_date
    while date < to_date:
        date = min(date + datetime.timedelta(days=90), to_date)
        date_partition.append(date)

    from_dates = date_partition[:1] + [date + datetime.timedelta(days=1) for date in date_partition[1:-1]] # Extra day added so no overlap between dates
    to_dates = date_partition[1:]
    date_partition = zip(from_dates, to_dates)
    return date_partition


# =================================================================================================================================================


def two_factor_authentication(driver):
    try:
        send_code_button = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, 'sendcode'))
        )
        ready_for_code = input('What is the authentication code?')
        if ready_for_code:
            send_code_button.click()
            # TODO: get details for authentication field
    except:
        print('Two factor authentication did not work')

def not_interested(driver):
    try:
        not_interested_button = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, 'action-link-class'))
        )
        not_interested_button.click()
    except:
        print('Unrecognised redirect link')


# =================================================================================================================================================


if __name__=='__main__':
    main()