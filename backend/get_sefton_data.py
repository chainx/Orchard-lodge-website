import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from datetime import datetime
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

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'OrchardLodge.settings.production')
import django
django.setup()

from django.conf import settings
from main.models import sefton_login_details

origin = 'https://providerportal.sefton.gov.uk'
base_url = origin + '/ProviderPortal_IAS_Live/secure/'

save_path = settings.MEDIA_REMITTANCE

options = Options()
options.add_argument('--headless')
options.set_preference("browser.download.folderList", 2)
options.set_preference("browser.download.manager.showWhenStarting", False)
options.set_preference("browser.download.dir", str(save_path))
options.set_preference("pdfjs.disabled", True)

def get_remittance_advice(period_id=None, download_csv=True, download_pdf=True):	   
    driver = webdriver.Firefox(options=options, service=Service(GeckoDriverManager().install()))

    SEFTON_LOGIN_DETAILS = sefton_login_details.objects.get(id=1)
    driver = login(driver, SEFTON_LOGIN_DETAILS.email, SEFTON_LOGIN_DETAILS.password, SEFTON_LOGIN_DETAILS.passcode)
    period_range = download_sefton_statements(driver, period_id, download_csv, download_pdf)

    filename = file_manipulation(period_range)
    return filename

def file_manipulation(period_range):
    year = datetime.now().strftime("%Y") # Folder structure is based on current date, not date of report
    period_range = ' - '.join([datetime.strptime(date,"%d/%m/%Y").strftime("%d %B") for date in period_range.split(' - ')])
    file_number = len(os.listdir(os.path.join(settings.MEDIA_REMITTANCE, year))) // 2 + 1
    filename = f'{file_number}. {period_range}'
    shutil.move(os.path.join(settings.MEDIA_REMITTANCE, 'report_export.csv'), os.path.join(settings.MEDIA_REMITTANCE, year, filename+'.csv'))
    shutil.move(os.path.join(settings.MEDIA_REMITTANCE, 'ActiveReports.PDF'), os.path.join(settings.MEDIA_REMITTANCE, year, filename+'.PDF'))
    return os.path.join(settings.MEDIA_REMITTANCE, year, filename+'.csv')

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

def download_sefton_statements(driver, period_id, download_csv, download_pdf):
    driver.get(base_url+'report.aspx?report=404001')

    contract_selection = Select(driver.find_element(By.ID, 'ContentPlaceHolderMain_repeaterParams_ContractID_0'))
    contract_selection.select_by_visible_text('Orchard Lodge Care Home')

    period_selection_element = driver.find_element(By.ID, "ContentPlaceHolderMain_repeaterParams_ContractPaymentPeriodID_2")
    period_range = period_selection_element.find_elements(By.TAG_NAME, 'option')[0].text
    if period_id:
        period_selection = Select(period_selection_element)
        period_selection.select_by_value(period_id)

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
    
    driver.quit()
    return period_range

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
