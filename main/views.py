import os
from datetime import datetime, date
import mimetypes
from zipfile import ZipFile

from urllib.request import HTTPRedirectHandler
from django.shortcuts import render, redirect
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib import messages
from django.core.files.storage import FileSystemStorage

from .forms import UploadFileForm, ResidentForm
from .models import resident, invoice, payment

from backend.file_utils import file_num, latest_filename, latest_filenum
from backend.get_sefton_data import get_remittance_advice
from backend.invoices import get_invoice_data_from_sefton_csv, write_invoices_and_update_db
from backend.payments import match_payments_to_resident
from backend.send_emails import send_email

from django.conf import settings

# Create your views here.
def home(request):
    year = datetime.now().strftime("%Y")
    latest_remittance = latest_filename(settings.MEDIA_REMITTANCE)

    if request.user.is_authenticated:
        if request.method=='POST':
            if request.POST['Sefton'] == 'Obtain latest invoices from Sefton':
                # Check if latest remittance advice matches latest invoice batch
                if latest_filenum(settings.MEDIA_REMITTANCE) != latest_filenum(settings.MEDIA_INVOICES):
                    return render(request, "main/remittance_advice.html", {'data': get_invoice_data_from_sefton_csv(latest_remittance)[0]})
                else:
                    filename = get_remittance_advice()
                    if filename: #filename returns None if new data isn't obtained
                        return render(request, "main/remittance_advice.html", {'data': get_invoice_data_from_sefton_csv(filename)[0]})
                    else:
                        return render(request, "main/home.html", {'new_data': not filename})
            if request.POST['Sefton'] == 'Confirm latest invoices from Sefton':

                invoices, batch_number, folder = get_invoice_data_from_sefton_csv(latest_remittance)
                write_invoices_and_update_db(invoices, batch_number, folder)
                # send_email() #Sends email to the manager with the recent batch of invoices

                return render(request, "main/home.html", {'confirmed_data': True})
        return render(request, "main/home.html")
    else:
        return redirect('/login')

def payments(request):
    if request.user.is_authenticated:
        data = {
            'unmatched_payments': payment.objects.filter(Resident_id__isnull=True, date__gte=date(2018,1,1)).order_by('date').reverse(),
            'residents': resident.objects.all(),
        }
        if request.method=='POST':
            filter_input = request.POST['filter_input']
            resident_id = request.POST['resident_id']
            multiple_matches = match_payments_to_resident(resident_id, filter_input)
            if multiple_matches:
                raise ValueError('Multiple matches!')
        return render(request, "main/payments.html", data)
    else:
        return redirect('/login')

def str_total(total):
    return u'\u00A3' + f'{total/100:,.2f}'

def compile_resident_table(residents, include_date_left=False):
    resident_table = []
    resident_list = sorted(list(residents), key = lambda x: x.total_owed(), reverse=True)
    for res in resident_list:
        if res.len_invoices()>0:
            row = [res, res.len_invoices(), str_total(res.total_invoiced()), res.len_payments(), str_total(res.total_payed()), str_total(res.total_owed())]
            if include_date_left:
                row.append(res.leave_date)
            resident_table.append(row)
    return resident_table

def residents(request):
    if request.user.is_authenticated:
        residents = resident.objects.exclude(first='Council').exclude(first='Cheques').order_by('last')
        data = {
            'resident_info_table':  compile_resident_table(residents.filter(current=True, private=False)),
            'private_resident_info_table': compile_resident_table(residents.filter(current=True, private=True)),
            'recent_resident_info_table': compile_resident_table(residents.filter(leave_date__gt=date(2023,1,1)), include_date_left=True),
            'former_residents' : residents.filter(current=False),
        }

        if request.method=='POST':
            form = ResidentForm(request.POST)
            if form.is_valid():
                form.save()
                return redirect('/residents')
        else:
            form = ResidentForm()
        data['resident_form']=form

        return render(request, "main/residents.html", data)
    else:
        return redirect('/login')

def specific_resident(request, res_url):
    if request.user.is_authenticated:
        title, first, last = res_url.split('-')
        res = resident.objects.get(title=title, first=first.replace('_', ' '), last=last.replace('_', ' '))
        
        data = {
            'res':res,
            'unmatched_invoices':res.invoice_set.filter(obsolete=False, matched=False).order_by('year', 'batch_number').reverse(),
            'unmatched_payments':res.payment_set.filter(matched=False).order_by('date').reverse(),
            'resident_form': ResidentForm(instance=res),
        }
        data['accepted_matches'] = []
        for index, payment_ in enumerate(res.payment_set.filter(matched=True).order_by('date').reverse()):
            data['accepted_matches'].append((index, payment_, payment_.invoice_set.all()))

        if request.method=='POST' and request.POST['form_type']=='Updating resident info':
            form = ResidentForm(request.POST, instance=res)
            if form.is_valid():
                data['resident_form'] = form
                form.save()

        if request.method=='POST' and request.POST['form_type']=='Payment matching':
            payments_matched = {int(key.split(' - ')[1]): value.split('-') for key, value in request.POST.items() if 'Payment ID' in key and value != ''}
            for payment_id, invoice_ids in payments_matched.items():
                payment_ = payment.objects.get(id=payment_id)
                for invoice_ in invoice.objects.filter(id__in=invoice_ids):
                    invoice_.matched = True
                    payment_.matched = True
                    invoice_.Payment.add(payment_)
                    invoice_.save()
                    payment_.save()

        return render(request, "main/specific_resident.html", data)
    else:
        return redirect('/login')
    
def cash_and_cheques(request):
    data = {}
    return render(request, "main/cash_and_cheques.html", data)

def upload(request):
    if request.user.is_authenticated:
        if request.method == 'POST':
            form = UploadFileForm(request.POST,request.FILES)
            files = request.FILES.getlist('filename')
            if form.is_valid():
                for f in files:
                    invoice(filename=f).save() #Modify this to add further info using data in invoice
                return redirect('home')
        else:
            form = UploadFileForm()
        return render(request, 'main/upload.html', {'form':form})
    else:
        return redirect('/login')

def download(request):
    if request.user.is_authenticated:
        if request.method == 'POST':
            file = request.POST['File']
            filename = file.split('/')[-1]

            #Need to create zips for older folders

            mime_type, _ = mimetypes.guess_type(file)
            with open(file, 'rb') as file:
                response = HttpResponse(file, content_type=mime_type)
            response['Content-Disposition'] = "attachment; filename=%s" % filename
            return response
        else:
            data = {'years' : {year : {file : 'Invoices/'+year+'/'+file+'.zip' for file in sorted(os.listdir('Invoices/'+year),key=file_num) if '.zip' not in file} for year in os.listdir('Invoices')[::-1] if len(year)==4}}
            return render(request, "main/download.html", data)
    else:
        return redirect('/login')