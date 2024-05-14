import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import datetime, date
import shutil
import json
import string
import secrets

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from webdriver_manager.firefox import GeckoDriverManager

import django
django.setup()

from django.conf import settings
from main.models import sefton_login_details

origin = 'https://providerportal.sefton.gov.uk'
base_url = origin + '/ProviderPortal_IAS_Live/secure/'

options = Options()
options.add_argument('--headless')
options.set_preference("browser.download.folderList", 2)
options.set_preference("browser.download.manager.showWhenStarting", False)
options.set_preference("browser.download.dir", str(settings.MEDIA_REMITTANCE))
options.set_preference("pdfjs.disabled", True)

def get_remittance_advice(period_id=None, download_csv=True, download_pdf=True):	   
    driver = webdriver.Firefox(options=options, service=Service(GeckoDriverManager().install()))
    SEFTON_LOGIN_DETAILS = sefton_login_details.objects.get(id=1)
    driver = login(driver, SEFTON_LOGIN_DETAILS.email, SEFTON_LOGIN_DETAILS.password, SEFTON_LOGIN_DETAILS.passcode)
    period_range = download_sefton_statements(driver, period_id, download_csv, download_pdf)
    driver.quit()

    filename = file_manipulation(period_range)
    return filename

def get_historical_remittance_advice(min_date, max_date):
    driver = webdriver.Firefox(options=options, service=Service(GeckoDriverManager().install()))
    SEFTON_LOGIN_DETAILS = sefton_login_details.objects.get(id=1)
    driver = login(driver, SEFTON_LOGIN_DETAILS.email, SEFTON_LOGIN_DETAILS.password, SEFTON_LOGIN_DETAILS.passcode)
    
    period_ids = download_sefton_statements(driver, min_date=min_date, max_date=max_date)
    for period_id in period_ids:
        period_range = download_sefton_statements(driver, period_id)
        file_manipulation(period_range)
    driver.quit()

def file_manipulation(period_range):
    year = period_range.split(' - ')[1].split('/')[-1]
    period_range = ' - '.join([datetime.strptime(date,"%d/%m/%Y").strftime("%d %B") for date in period_range.split(' - ')])
    dir = os.path.join(settings.MEDIA_REMITTANCE, year)
    os.makedirs(dir, exist_ok=True)
    file_number = len(os.listdir(dir)) // 2 + 1
    filename = f'{file_number}. {period_range}'
    shutil.move(os.path.join(settings.MEDIA_REMITTANCE, 'report_export.csv'), os.path.join(settings.MEDIA_REMITTANCE, year, filename+'.csv'))
    shutil.move(os.path.join(settings.MEDIA_REMITTANCE, 'ActiveReports.PDF'), os.path.join(settings.MEDIA_REMITTANCE, year, filename+'.PDF'))
    return os.path.join(settings.MEDIA_REMITTANCE, year, filename+'.csv')


# ======================================================================================================================


def login(driver, email, password, passcode):                  
    driver.get(base_url+'home.aspx')

    email_field = driver.find_element(By.ID, 'ContentPlaceHolderMain_txtEmail')
    password_field = driver.find_element(By.ID, 'ContentPlaceHolderMain_txtPassword')
    email_field.send_keys(email)
    password_field.send_keys(password)

    login_button = driver.find_element(By.ID, 'ContentPlaceHolderMain_btnLogin')
    login_button.click()

    if driver.current_url != base_url + 'loginsecuritycode.aspx?redirect=providerselect.aspx':
        update_password_from_webpage(driver, password)

    first_digit_value = driver.find_element(By.ID, 'ContentPlaceHolderMain_lblSecurityCodePromptDigit1').text[0]
    first_digit_field = driver.find_element(By.ID, 'ContentPlaceHolderMain_validatingDropDownListDigit1')
    Select(first_digit_field).select_by_visible_text(passcode[int(first_digit_value)-1])
    second_digit_value = driver.find_element(By.ID, 'ContentPlaceHolderMain_lblSecurityCodePromptDigit2').text[0]
    second_digit_field = driver.find_element(By.ID, 'ContentPlaceHolderMain_validatingDropDownListDigit2')
    Select(second_digit_field).select_by_visible_text(passcode[int(second_digit_value)-1])

    submit_button = driver.find_element(By.ID, 'ContentPlaceHolderMain_btnOK')
    submit_button.click()

    return driver

def download_sefton_statements(driver, period_id=None, download_csv=True, download_pdf=True, min_date=None, max_date=None):
    driver.get(base_url+'report.aspx?report=404001')

    contract_selection = Select(driver.find_element(By.ID, 'ContentPlaceHolderMain_repeaterParams_ContractID_0'))
    contract_selection.select_by_visible_text('Orchard Lodge Care Home')

    period_selection_element = driver.find_element(By.ID, "ContentPlaceHolderMain_repeaterParams_ContractPaymentPeriodID_2")
    period_selection = Select(period_selection_element)
    if period_id:
        period_selection.select_by_value(period_id)
    if min_date or max_date:
        return [option.get_attribute('value') for option in period_selection.options if filter_options(option, min_date, max_date)][::-1]
    period_range = period_selection.first_selected_option.text

    if download_csv:
        download_csv_button = driver.find_element(By.ID, 'ContentPlaceHolderMain_btnDownload')
        download_csv_button.click()

    if download_pdf:
        generate_pdf_button = driver.find_element(By.ID, 'ContentPlaceHolderMain_btnView')
        generate_pdf_button.click()

        wait = WebDriverWait(driver, 10)
        wait.until(expected_conditions.presence_of_element_located((By.TAG_NAME, 'iframe')))
        pdf_url = driver.find_element(By.TAG_NAME, 'iframe').get_attribute("src")
        
        try: # Hacky way of dealing with the fact that driver.get(pdf_url) stalls when "pdfjs.disabled" is set to True
            wait = WebDriverWait(driver, 0.1)
            wait.until(expected_conditions.presence_of_element_located((By.XPATH, '//*[@id="download"]')))
            driver.get(pdf_url)
        except:
            pass
    
    return period_range

def filter_options(option, min_date, max_date):
    keep = True
    end_date = datetime.strptime(option.text.split(' - ')[1], '%d/%m/%Y').date()
    if min_date:
        keep = keep and end_date >= min_date
    if max_date:
        keep = keep and end_date <= max_date
    return keep

def update_password_from_webpage(driver, password):
    new_password = generate_new_password()

    current_password_field = driver.find_element(By.ID, 'ContentPlaceHolderMain_tbCurrent')
    current_password_field.send_keys(password)
    new_password_field = driver.find_element(By.ID, 'ContentPlaceHolderMain_tbNewPassword')
    new_password_field.send_keys(new_password)
    confirm_password_field = driver.find_element(By.ID, 'ContentPlaceHolderMain_tbConfirm')
    confirm_password_field.send_keys(new_password)

    submit_button = driver.find_element(By.ID, 'ContentPlaceHolderMain_btnOK')
    submit_button.click()

    return new_password

def generate_new_password():
    symbols = ['*', '%', '$','!',',','?','.','(',')']
    new_password = ''
    for _ in range(16):
        n=secrets.choice([1,2,3,4,5,6])
        if n==1 or n==2:
            new_password += secrets.choice(string.ascii_lowercase)
        if n==3 or n==4:
            new_password += secrets.choice(string.ascii_uppercase)
        if n==5:
            new_password += secrets.choice(string.digits)
        if n==6:
            new_password += secrets.choice(symbols)
    
    #Update Sefton_login_details.json file with new password
    SEFTON_LOGIN_DETAILS = sefton_login_details.objects.get(id=1)
    SEFTON_LOGIN_DETAILS.password = new_password
    SEFTON_LOGIN_DETAILS.save()

    return new_password

if __name__ == "__main__":
    get_remittance_advice()
    # get_historical_remittance_advice(date(2017,12,31), date(2022,1,1))
