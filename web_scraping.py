from bs4 import BeautifulSoup as soup
from datetime import datetime
import requests
import os
import json
import string
import secrets



base_url = 'https://providerportal.sefton.gov.uk/ProviderPortal_IAS_Live/secure/'

def generate_new_password(password, file_data):
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
  
  #Update .INSTRUCTIONS.txt file with new password
  file_data[2] = f"Password = {new_password}\n"
  with open('.INSTRUCTIONS.txt', 'w') as file:
      file.writelines(file_data)

  return new_password

def add_hidden_info(data,page):
  for input in page.find_all("input",type="hidden"):
    data[input['name']]=input['value']
  return data

def scrape_data():
  #Get password and passcode
  Sefton_login_details = json.load(open('Sefton_login_details.json'))
  email = Sefton_login_details['Email']
  password = Sefton_login_details['Password']
  passcode = Sefton_login_details['6 digit code']

  with requests.Session() as session:
    #============================================================= LOGIN WITH EMAIL AND PASSWORD ======================================================================================================================

    response = session.get(base_url+'login.aspx')

    form = {
      '_ctl0:ContentPlaceHolderMain:txtEmail': email,
      '_ctl0:ContentPlaceHolderMain:txtPassword': password,
      '_ctl0:ContentPlaceHolderMain:btnLogin': 'Login'}
    page = soup(response.text,'html.parser')
    form = add_hidden_info(form,page)
    headers = {'Referer': base_url+'login.aspx'}

    response = session.post(base_url+'login.aspx', headers=headers, data=form)
    page=soup(response.text,'html.parser')

    #========================================================== CHECK IF PASSWORD NEEDS UPDATING AND IF SO UPDATE =====================================================================================================
    
    if page.find(id="ContentPlaceHolderMain_tbNewPassword"):
      new_password = 'lol'#generate_new_password(password, file_data)

      password_form = {
        '_ctl0:ContentPlaceHolderMain:tbCurrent': password,
        '_ctl0:ContentPlaceHolderMain_tbNewPassword': new_password,
        '_ctl0:ContentPlaceHolderMain_tbConfirm': new_password,
        '_ctl0:ContentPlaceHolderMain:btnOK': 'OK'
      }
      
      password_form = add_hidden_info(password_form,page)
      headers['Referer'] = base_url + 'loginsecuritycode.aspx' #'login.aspx?ReturnUrl=/ProviderPortalLIVE/secure/changepassword.aspx?redirect=providerselect.aspx&redirect=providerselect.aspx'
      params = (('redirect', 'providerselect.aspx'),)

      response = session.post(base_url+'loginsecuritycode.aspx', data=password_form)
      print(response)
      page=soup(response.text,'html.parser')
      print(page)

    #========================================================= ENTER PASSCODE DIGITS TO COMPLETE LOGIN ================================================================================================================

    digit1 = int(page.find(id="ContentPlaceHolderMain_lblSecurityCodePromptDigit1").text[0])
    digit2 = int(page.find(id="ContentPlaceHolderMain_lblSecurityCodePromptDigit2").text[0])
    digit_form = {
      '_ctl0:ContentPlaceHolderMain:validatingDropDownListDigit1': passcode[digit1-1],
      '_ctl0:ContentPlaceHolderMain:validatingDropDownListDigit2': passcode[digit2-1],
      '_ctl0:ContentPlaceHolderMain:btnOK': 'OK'
    }
    digit_form = add_hidden_info(digit_form,page)
    headers['Referer'] = base_url+'loginsecuritycode.aspx'
    params = (('redirect', 'providerselect.aspx'),)

    response = session.post(base_url+'loginsecuritycode.aspx', headers=headers, params=params, data=digit_form)

    #======================================================= REQUEST REMITTANCE ADVICE CSV FILES ======================================================================================================================

    data = {
      '_ctl0:ContentPlaceHolderMain:repeaterParams:_ctl1:Contract': '120',
      '_ctl0:ContentPlaceHolderMain:repeaterParams:_ctl2:PaymentMethod': '121',
    }
    response = session.get(base_url+'report.aspx?report=404001')
    page=soup(response.text,'html.parser')
    data = add_hidden_info(data,page)
    
    response = session.post(base_url+'report.aspx?report=404001',data=data)
    page=soup(response.text,'html.parser')
    tag = page.find(id="ContentPlaceHolderMain_repeaterParams_ContractPaymentPeriodID_2").find("option",{'selected':'selected'})

    #data['_ctl0:ContentPlaceHolderMain:repeaterParams:_ctl3:ContractPaymentPeriodID'] = '14438' #SET PERIOD ID using .find("option",{'value':'PERIOD ID'})
    data['_ctl0:ContentPlaceHolderMain:btnDownload'] = 'Download Data'
    response = session.post(base_url+'report.aspx?report=404001',data=data)

    #========================================================= WRITE THE CONTENT INTO A FILE ==========================================================================================================================

    #Creating necessary folders if they don't already exist
    year = datetime.now().strftime("%Y")
    if year not in os.listdir('Remittance advice'):
      os.makedirs('Remittance advice/'+year)
    
    file_number = str(len(os.listdir('Remittance advice/'+year)) + 1)
    dates = [datetime.strptime(date,"%d/%m/%Y").strftime("%d %B") for date in tag.text[2:].split(' - ')]
    filename = 'Remittance advice/'+year+'/'+file_number+'. '+' - '.join(dates)+'.csv'
    
    #If the data is old return None, otherwise write it to a csv file
    if any([' - '.join(dates) in file for file in os.listdir('Remittance advice/'+year)]):
      filename = None
    else:
      with open(filename,'wb') as f:
        f.write(response.content)

  return filename #tag['value'] returns batch ID

if __name__ == "__main__":
  scrape_data()