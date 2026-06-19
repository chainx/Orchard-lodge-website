import os
import pandas as pd
from datetime import datetime, date
import mimetypes
import tempfile
from zipfile import ZipFile
from zoneinfo import ZoneInfo

from urllib.request import HTTPRedirectHandler
from django.shortcuts import render, redirect
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib import messages
from django.core.files.storage import FileSystemStorage
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .forms import UploadFileForm, ResidentForm
from .models import global_variables, resident, invoice, payment, sefton_action_item as sefton_action_item_model

from backend.file_utils import file_num, latest_filename, latest_filenum
from backend.get_sefton_data import get_latest_action_items, get_remittance_advice
from backend.invoices import get_invoice_data_from_sefton_csv, write_invoices_and_update_db, generate_unique_customer_reference_number
from backend.payments import match_payments_to_resident, normalize_payment_filters, update_payments
from backend.statement_of_account import can_convert_to_pdf, merge_pdfs, write_cover_letter, write_statement_of_account

from django.conf import settings

SEFTON_TIMEZONE = ZoneInfo('Europe/London')

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

                return render(request, "main/home.html", {'confirmed_data': True})
        return render(request, "main/home.html")
    else:
        return redirect('/login')

def payments(request):
    if request.user.is_authenticated:
        variables = global_variables.load()
        cutoff_date = variables.unmatched_payment_cutoff_date
        data = {
            'unmatched_payments': payment.objects.filter(Resident_id__isnull=True, date__gte=cutoff_date).order_by('date').reverse(),
            'residents': resident.objects.all(),
            'last_downloaded_at': format_london_datetime(variables.last_bank_statement_downloaded_at),
        }
        if request.method=='POST':
            if request.POST.get('form_type') == 'Update payments':
                try:
                    new_payments = update_payments()
                except Exception as error:
                    messages.error(request, f'Payment update failed: {error}')
                    return redirect('/payments/')
                request.session['new_payments'] = payments_to_session_records(new_payments)
                return redirect('/payments/new/')

            filter_input = request.POST['filter_input'].strip()
            resident_id = request.POST['resident_id']
            if filter_input and resident_id:
                res = resident.objects.get(id=resident_id)
                try:
                    with transaction.atomic():
                        filters = normalize_payment_filters(res.filters) + normalize_payment_filters(filter_input)
                        filters = list(dict.fromkeys(filters))
                        res.filters = ';'.join(filters)
                        res.save()
                        match_payments_to_resident(res.id, filter_input, res.name)
                except Exception as error:
                    messages.error(request, f'Payment filter failed: {error}')
                return redirect('/payments')
        return render(request, "main/payments.html", data)
    else:
        return redirect('/login')

def payments_to_session_records(payments_df):
    records = []
    for payment_ in payments_df.to_dict(orient='records'):
        payment_date = payment_['date']
        if hasattr(payment_date, 'strftime'):
            payment_date = payment_date.strftime('%d/%m/%Y')

        records.append({
            'date': payment_date,
            'description': payment_['description'],
            'amount': str_total(payment_['amount']),
        })
    return records

def new_payments(request):
    if request.user.is_authenticated:
        return render(request, "main/new_payments.html", {
            'new_payments': request.session.get('new_payments', []),
        })
    else:
        return redirect('/login')

def sefton_action_items(request):
    if request.user.is_authenticated:
        if request.method == 'POST':
            if request.POST.get('form_type') == 'Update action items':
                get_latest_action_items()
                return redirect('/sefton-action-items/')

        variables = global_variables.load()
        data = {
            'action_items': sefton_action_item_model.objects.order_by('-last_post_at', 'title'),
            'last_downloaded_at': format_london_datetime(variables.last_action_item_downloaded_at),
        }
        return render(request, "main/sefton_action_items.html", data)
    else:
        return redirect('/login')

def sefton_action_item(request, action_id):
    if request.user.is_authenticated:
        action_item = sefton_action_item_model.objects.get(action_id=action_id)
        data = {
            'action_item': action_item,
            'conversation_posts': format_action_item_conversation(action_item.conversation),
        }
        return render(request, "main/sefton_action_item.html", data)
    else:
        return redirect('/login')

def format_action_item_conversation(conversation):
    posts = []
    for post in conversation:
        sent_at = parse_datetime(post.get('sent_at', ''))

        posts.append({
            **post,
            'sent_at': format_london_datetime(sent_at, empty_value=post.get('sent_at', '')),
        })
    return posts

def format_london_datetime(value, empty_value='Never downloaded'):
    if value is None:
        return empty_value

    if timezone.is_aware(value):
        value = value.astimezone(SEFTON_TIMEZONE)
    else:
        value = timezone.make_aware(value, SEFTON_TIMEZONE)
    return value.strftime('%d/%m/%Y %H:%M')

def str_total(total):
    return u'\u00A3' + f'{total/100:,.2f}'

def compile_resident_table(residents, include_date_left=False):
    columns = ['index', 'res', 'invoice_no', 'invoice_total', 'payment_no', 'payment_total', 'owed', 'sefton_payment_total']
    summable_cols = columns[2:]
    if include_date_left:
            columns.insert(2, 'leave_date')
    
    resident_table = pd.DataFrame(columns=columns)

    resident_list = sorted(list(residents), key = lambda x: x.total_owed(), reverse=True)
    for index, res in enumerate(resident_list):
        row = [
            index+1, res, res.len_invoices(), res.total_invoiced(), res.len_payments(), 
            res.total_payed(), res.total_owed(), res.total_sefton_payed()
        ]
        if include_date_left:
            row.insert(2, res.leave_date)
        resident_table.loc[len(resident_table)] = row

    totals_row = [resident_table[col].sum() for col in summable_cols]
    if include_date_left:
        totals_row = ['', 'Total', pd.NaT] + totals_row
    else:
        totals_row = ['', 'Total'] + totals_row
    resident_table.loc[len(resident_table)] = totals_row

    for col in ['invoice_total', 'payment_total', 'owed', 'sefton_payment_total']:
        resident_table[col] = resident_table[col].apply(str_total)
    
    return resident_table.to_dict(orient='records')

def continue_resident_table_indices(*resident_tables):
    index = 1
    for resident_table in resident_tables:
        for row in resident_table:
            if row['res'] != 'Total':
                row['index'] = index
                index += 1

def residents(request):
    if request.user.is_authenticated:
        cutoff_date = global_variables.load().recently_left_cutoff_date
        residents = resident.objects.exclude(first='Council').exclude(first='Cheques').order_by('last')
        private_resident_info_table = compile_resident_table(residents.filter(current=True, private=True))
        resident_info_table = compile_resident_table(residents.filter(current=True, private=False))
        continue_resident_table_indices(private_resident_info_table, resident_info_table)
        data = {
            'resident_info_table':  resident_info_table,
            'private_resident_info_table': private_resident_info_table,
            'recent_resident_info_table': compile_resident_table(residents.filter(leave_date__gt=cutoff_date), include_date_left=True),
            'former_residents' : residents.filter(current=False),
        }

        if request.method=='POST':
            post_data = request.POST.copy()  # Make the POST data mutable
            post_data['customer_ref_no'] = generate_unique_customer_reference_number()
            post_data['current'] = True
            form = ResidentForm(post_data)
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
        cutoff_date = global_variables.load().payments_invoices_cutoff_date
        title, first, last = res_url.split('-')
        res = resident.objects.get(title=title, first=first.replace('_', ' '), last=last.replace('_', ' '))
        
        data = {
            'res':res,
            'unmatched_invoices':res.invoice_set.filter(obsolete=False, matched=False).order_by('date').filter(date__gte=cutoff_date),#.reverse(),
            'unmatched_payments':res.payment_set.filter(matched=False).order_by('date').filter(date__gte=cutoff_date),#.reverse(),
            'sefton_payments': res.sefton_payment_set.order_by('date').filter(date__gte=cutoff_date),#.reverse(),
            'resident_form': ResidentForm(instance=res),
        }
        data['accepted_matches'] = []
        for index, payment_ in enumerate(res.payment_set.filter(matched=True)):
            data['accepted_matches'].append((index, payment_, payment_.invoice_set.all(), payment_.invoice_set.latest('date').date))
        data['accepted_matches'] = sorted(data['accepted_matches'], key=lambda x: x[-1])

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

def download_statement_of_account(request, res_url):
    if request.user.is_authenticated:
        title, first, last = res_url.split('-')
        res = resident.objects.get(title=title, first=first.replace('_', ' '), last=last.replace('_', ' '))
        include_cover_letter = request.GET.get('include_cover_letter') == 'on'

        with tempfile.TemporaryDirectory() as folder:
            filename = create_downloadable_statement(folder, res, include_cover_letter)
            with open(filename, 'rb') as download_file:
                content_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
                response = HttpResponse(download_file.read(), content_type=content_type)

        download_filename = os.path.basename(filename)
        response['Content-Disposition'] = f'attachment; filename="{download_filename}"'
        return response
    else:
        return redirect('/login')

def create_downloadable_statement(folder, res, include_cover_letter):
    try:
        return create_downloadable_statement_files(folder, res, include_cover_letter, convert_to_pdf=can_convert_to_pdf())
    except RuntimeError:
        return create_downloadable_statement_files(folder, res, include_cover_letter, convert_to_pdf=False)

def create_downloadable_statement_files(folder, res, include_cover_letter, convert_to_pdf):
    statement = write_statement_of_account(folder, 1, res, convert_to_pdf=convert_to_pdf)
    if not include_cover_letter:
        return statement

    cover_letter = write_cover_letter(folder, 1, res, convert_to_pdf=convert_to_pdf)
    if cover_letter is None:
        return statement

    if convert_to_pdf:
        merge_pdfs(cover_letter, statement)
        return statement

    zip_filename = os.path.join(folder, f'{res.name} - Statement of Account.zip')
    with ZipFile(zip_filename, 'w') as zip_file:
        zip_file.write(cover_letter, os.path.basename(cover_letter))
        zip_file.write(statement, os.path.basename(statement))
    return zip_filename
     
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
