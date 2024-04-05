import os
from datetime import datetime
import mimetypes
from zipfile import ZipFile

from urllib.request import HTTPRedirectHandler
from django.shortcuts import render, redirect
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib import messages
from django.core.files.storage import FileSystemStorage

from .forms import UploadFileForm, ResidentForm
from .models import resident, invoice, payment

from backend.utils import file_num, get_latest, latest_num
from backend.get_sefton_data import get_remittance_advice
from backend.invoices import get_invoice_data_from_sefton_csv, write_invoices_and_update_db
from backend.payments import match_payments_to_resident
from backend.send_emails import send_email

from django.conf import settings

# Create your views here.
def home(request):
    year = datetime.now().strftime("%Y")
    latest_remittance = get_latest(settings.MEDIA_REMITTANCE)

    if request.user.is_authenticated:
        if request.method=='POST':
            if request.POST['Sefton'] == 'Obtain latest invoices from Sefton':
                # Check if latest remittance advice matches latest invoice batch
                if latest_num(settings.MEDIA_REMITTANCE) != latest_num(settings.MEDIA_INVOICES):
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
            'unmatched_payments': payment.objects.filter(Resident_id__isnull=True).order_by('date').reverse(),
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
    
def residents(request):
    if request.user.is_authenticated:
        residents = resident.objects.exclude(first='Council').exclude(first='Cheques').order_by('last')
        data = {
            'current_residents' : residents.filter(current=True, private=False),
            'private_residents' : residents.filter(current=True, private=True),
            'former_residents' : residents.filter(current=False),
        }
        if request.method=='POST':
            form = ResidentForm(request.POST)
            if form.is_valid():
                form.save()
                return redirect('/residents')
        else:
            form = ResidentForm()
        data['form']=form
        return render(request, "main/residents.html", data)
    else:
        return redirect('/login')

def specific_resident(request, res_url):
    if request.user.is_authenticated:
        name=res_url.split('-')
        res = resident.objects.get(title=name[0], first=' '.join(name[1:-1]),last=name[-1])
        data = {
            'res':res,
            'matched_invoices':res.invoice_set.filter(obsolete=False, matched=True).order_by('year', 'batch_number').reverse(),
            'matched_payments':res.payment_set.filter(matched=True).order_by('date').reverse(),
            'unmatched_invoices':res.invoice_set.filter(obsolete=False, matched=False).order_by('year', 'batch_number').reverse(),
            'unmatched_payments':res.payment_set.filter(matched=False).order_by('date').reverse(),
            'resident_form': ResidentForm(instance=res),
        }

        if request.method=='POST' and request.POST['form_type']=='Updating resident info':
            form = ResidentForm(request.POST, instance=res)
            if form.is_valid():
                data['resident_form'] = form
                form.save()
                return render(request, "main/specific_resident.html", data)

        if request.method=='POST' and request.POST['form_type']=='Payment matching':
            payments_matched = {int(key.split(' - ')[1]): int(value) for key, value in request.POST.items() if 'Payment ID' in key and value != ''}
            for invoice_id, payment_id in payments_matched.items():
                invoice_ = invoice.objects.get(id=invoice_id)
                payments = payment.objects.filter(id=payment_id)

                invoice_.matched = True
                invoice_.save()
                payments.update(matched=True)
                invoice_.Payment.set(payments)
                return render(request, "main/specific_resident.html", data)

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