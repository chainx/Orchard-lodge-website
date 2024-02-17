from datetime import datetime
import os
import json
import string
import secrets
import time

from bs4 import BeautifulSoup as soup
import requests
from requests_html import HTMLSession


origin = 'https://providerportal.sefton.gov.uk'
base_url = origin + '/ProviderPortal_IAS_Live/secure/'

def add_hidden_info(data, response):
	page=soup(response.text,'html.parser')
	for input in page.find_all("input", type="hidden"):
		data[input['name']]=input['value']
	return data

def scrape_data(period_id=None):
	#Get password and passcode
	Sefton_login_details = json.load(open('Sefton_login_details.json'))
	email = Sefton_login_details['Email']
	password = Sefton_login_details['Password']
	passcode = Sefton_login_details['6 digit code']

	with requests.Session() as session:
	# with HTMLSession() as session:

	#============================================================= LOGIN WITH EMAIL AND PASSWORD ======================================================================================================================

		response = session.get(base_url+'home.aspx', verify='Sefton_ssl_certificate.crt')

		form = {
			'_ctl0:ContentPlaceHolderMain:txtEmail': email,
			'_ctl0:ContentPlaceHolderMain:txtPassword': password,
			'_ctl0:ContentPlaceHolderMain:btnLogin': 'Login'}
		form = add_hidden_info(form, response)
		headers = {'Referer': base_url+'home.aspx'}

		response = session.post(base_url+'home.aspx', headers=headers, data=form, allow_redirects=True)
		page=soup(response.text,'html.parser')

		# Check if password needs updating and if so update
		if page.find(id="ContentPlaceHolderMain_tbNewPassword"):
			update_password(session, response, password)

	#========================================================= ENTER PASSCODE DIGITS TO COMPLETE LOGIN ================================================================================================================

		digit1 = int(page.find(id="ContentPlaceHolderMain_lblSecurityCodePromptDigit1").text[0])
		digit2 = int(page.find(id="ContentPlaceHolderMain_lblSecurityCodePromptDigit2").text[0])
		digit_form = {
			'_ctl0:ContentPlaceHolderMain:validatingDropDownListDigit1': passcode[digit1-1],
			'_ctl0:ContentPlaceHolderMain:validatingDropDownListDigit2': passcode[digit2-1],
			'_ctl0:ContentPlaceHolderMain:btnOK': 'OK'
		}
		digit_form = add_hidden_info(digit_form, response)
		headers['Referer'] = base_url+'loginsecuritycode.aspx'
		params = (('redirect', 'reportselect.aspx'),)

		response = session.post(base_url+'loginsecuritycode.aspx', headers=headers, params=params, data=digit_form)

	#======================================================= REQUEST REMITTANCE ADVICE CSV FILES ======================================================================================================================

		data = {
			'_ctl0:ContentPlaceHolderMain:repeaterParams:_ctl1:ContractID': '120',
			'_ctl0:ContentPlaceHolderMain:repeaterParams:_ctl2:PaymentMethod': '121',
		}
		response = session.get(base_url+'report.aspx?report=404001')
		data = add_hidden_info(data, response)

		response = session.post(base_url+'report.aspx?report=404001',data=data)
		page=soup(response.text,'html.parser')
		tag = page.find(id="ContentPlaceHolderMain_repeaterParams_ContractPaymentPeriodID_2").find("option",{'selected':'selected'})

		if period_id:
			data['_ctl0:ContentPlaceHolderMain:repeaterParams:_ctl3:ContractPaymentPeriodID'] = period_id

		data['_ctl0:ContentPlaceHolderMain:btnDownload'] = 'Download Data'
		response = session.post(base_url+'report.aspx?report=404001', data=data)

	#======================================================= ATTEMPTS TO GENERATE DOWNLOAD LINK FOR REMITTANCE ADVICE PDF ==============================================================================================

		# x=session.post('https://providerportal.sefton.gov.uk/ProviderPortal_IAS_Live/ActiveReports.ReportService.asmx/RunReport?Token=6c3ce4b6-c18d-44d6-ac65-07aff74983b7')
		# time.sleep(5)
		# y=session.post('https://providerportal.sefton.gov.uk/ProviderPortal_IAS_Live/ActiveReports.ReportService.asmx/GetExportedReportLink?Token=6c3ce4b6-c18d-44d6-ac65-07aff74983b7')

		# data['_ctl0:ContentPlaceHolderMain:btnView'] = 'View'
		# response = session.post(base_url+'report.aspx?report=404001',data=data)
		# page=soup(response.html.raw_html,'html.parser')
		# print(page.find(id="ContentPlaceHolderMain__controlDiv").contents)
		# response.html.render(sleep=3)
		# page=soup(response.html.raw_html,'html.parser')
		# print(page.find(id="ContentPlaceHolderMain__controlDiv").contents)

	filename = save_data(response.content, tag)
	return filename

def save_data(content, tag, force_write=False):
	#Creating necessary folders if they don't already exist
	year = datetime.now().strftime("%Y")
	if year not in os.listdir('Remittance advice'):
		os.makedirs('Remittance advice/'+year)

	file_number = str(len(os.listdir('Remittance advice/'+year)) + 1)
	dates = [datetime.strptime(date,"%d/%m/%Y").strftime("%d %B") for date in tag.text[2:].split(' - ')]
	filename = 'Remittance advice/'+year+'/'+file_number+'. '+' - '.join(dates)+'.csv'

	#If the data is old return None, otherwise write it to a csv file
	data_already_saved = any([' - '.join(dates) in file for file in os.listdir('Remittance advice/'+year)])
	if data_already_saved and not force_write:
		filename = None
	else:
		with open(filename,'wb') as f:
			f.write(content)

	return filename #tag['value'] returns batch ID

def update_password(session, response, password, file_data):
	new_password = generate_new_password(password, file_data)

	password_form = {
		'_ctl0:ContentPlaceHolderMain:tbCurrent': password,
		'_ctl0:ContentPlaceHolderMain_tbNewPassword': new_password,
		'_ctl0:ContentPlaceHolderMain_tbConfirm': new_password,
		'_ctl0:ContentPlaceHolderMain:btnOK': 'OK'
	}
	
	password_form = add_hidden_info(password_form, response)
	# headers['Referer'] = base_url + 'loginsecuritycode.aspx' #'login.aspx?ReturnUrl=/ProviderPortalLIVE/secure/changepassword.aspx?redirect=providerselect.aspx&redirect=providerselect.aspx'
	params = (('redirect', 'providerselect.aspx'),)

	response = session.post(base_url+'loginsecuritycode.aspx', data=password_form)
	return response

def generate_new_password(password):
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

	print(password)
	print(new_password)
  
	#Update Sefton_login_details.json file with new password
	with open('Sefton_login_details.json') as file:
		Sefton_login_details = json.load(file)
		Sefton_login_details['Password'] = new_password
		json.dump(Sefton_login_details, file)

	return new_password

if __name__ == "__main__":
	scrape_data()