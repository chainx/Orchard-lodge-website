import datetime

from django.db import models
from django.core.validators import MinLengthValidator

def payments_invoices_cutoff_date():
    return global_variables.load().payments_invoices_cutoff_date

class resident(models.Model):
    title = models.CharField(max_length=8)
    first = models.CharField(max_length=32)
    last = models.CharField(max_length=32)
    email = models.EmailField(max_length=256, default='', blank=True)
    email_name = models.CharField(max_length=64, default='', blank=True)
    customer_ref_no = models.CharField(max_length=6, default='', blank=True, null=True)
    sefton_id = models.CharField(max_length=32, blank=True, null=True)
    current = models.BooleanField(default=True)
    private = models.BooleanField(default=False)
    private_rate = models.IntegerField(default=0, blank=True, null=True)
    filters = models.CharField(max_length=256, default='', blank=True, null=True)
    start_date = models.DateField(blank=True, null=True)
    leave_date = models.DateField(blank=True, null=True)

    @property
    def name(self):
        if self.title=='':
            return f'{self.first} {self.last}'
        return f'{self.title} {self.first} {self.last}'
    
    @property
    def url(self):
        return '-'.join([self.title, self.first.replace(' ', '_'), self.last.replace(' ', '_')])
    
    def total_invoiced(self):
        return sum([invoice_.total for invoice_ in self.invoice_set.filter(date__gte=payments_invoices_cutoff_date(), obsolete=False)])
    def total_payed(self):
        return sum([payment_.amount for payment_ in self.payment_set.filter(date__gte=payments_invoices_cutoff_date())])
    def total_owed(self):
        return self.total_invoiced() - self.total_payed()
    def len_invoices(self):
        return len(self.invoice_set.filter(date__gte=payments_invoices_cutoff_date(), obsolete=False))
    def len_payments(self):
        return len(self.payment_set.filter(date__gte=payments_invoices_cutoff_date()))
    def total_sefton_payed(self):
        return sum([payment_.total for payment_ in self.sefton_payment_set.filter(date__gte=payments_invoices_cutoff_date())])

    def __str__(self):
        return self.name

class payment(models.Model):
    Resident = models.ForeignKey(resident, on_delete=models.CASCADE, blank=True, null=True)

    date = models.DateField(blank=True, null=True)
    description = models.CharField(max_length=256, blank=True, null=True)
    amount = models.IntegerField(blank=True, null=True)
    matched = models.BooleanField(default=False, blank=True, null=True)

    cash='Cash'
    cheque='Cheque'
    card='Card'
    santander='Santander'
    rbs='RBS'
    type_choices = [(cash,cash),(cheque,cheque),(card,card),(santander, santander),(rbs, rbs)]
    type = models.CharField(max_length=9, choices=type_choices, blank=True, null=True)


    @property
    def str_amount(self):
        return u'\u00A3' + f'{self.amount/100:,.2f}'
    
    @property
    def cleaned_description(self):
        return self.description.split('FASTER PAYMENTS RECEIPT ')[-1] 

    def __str__(self):
        return self.description

class invoice(models.Model):
    Resident = models.ForeignKey(resident, on_delete=models.CASCADE, blank=True, null=True)
    Payment =  models.ManyToManyField(payment, blank=True) # null has no effect on many to many relationships
    
    filename = models.FileField(upload_to='Invoices/', blank=True, null=True)
    invoice_number = models.CharField(max_length=5, validators=[MinLengthValidator(5)],blank=True, null=True) # Must have length 5
    batch_number = models.IntegerField(blank=True, null=True)
    date = models.DateField(blank=True, null=True) # Date issued
    year = models.IntegerField(blank=True, null=True) # Year issued, used together with batch_number
    total = models.IntegerField(blank=True, null=True)
    obsolete = models.BooleanField(default=False, blank=True, null=True)
    matched = models.BooleanField(default=False, blank=True, null=True)

    @property
    def name(self):
        return self.Resident.name + str(self.invoice_number)
    
    @property
    def str_total(self):
        return u'\u00A3' + f'{self.total/100:,.2f}'

    def __str__(self):
        return str(self.filename)
    
class sefton_payment(models.Model):
    Resident = models.ForeignKey(resident, on_delete=models.CASCADE, blank=True, null=True)

    batch_number = models.IntegerField(blank=True, null=True)
    date = models.DateField(blank=True, null=True) # End date of remittance advice period
    year = models.IntegerField(blank=True, null=True)
    total = models.IntegerField(blank=True, null=True)
    
    @property
    def str_total(self):
        return u'\u00A3' + f'{self.total/100:,.2f}'
    
class sefton_login_details(models.Model):
    email = models.CharField(max_length=256, blank=True, null=True)
    password = models.CharField(max_length=256, blank=True, null=True)
    passcode = models.CharField(max_length=6, blank=True, null=True)

class sefton_action_item(models.Model):
    action_id = models.CharField(max_length=64, unique=True)
    title = models.CharField(max_length=256)
    relates_to = models.CharField(max_length=256, blank=True)
    conversation = models.JSONField(default=list)
    downloaded_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f'{self.action_id}: {self.title}'

def default_cover_letter_thresholds():
    return {'lower': 0, 'upper': 1e8, 'urgent_upper': 1e10}

class global_variables(models.Model):
    last_bank_statement_downloaded_at = models.DateTimeField(blank=True, null=True)
    last_remittance_advice_downloaded_at = models.DateTimeField(blank=True, null=True)
    last_action_item_downloaded_at = models.DateTimeField(blank=True, null=True)
    payments_invoices_cutoff_date = models.DateField(default=datetime.date(2023, 3, 1))
    recently_left_cutoff_date = models.DateField(default=datetime.date(2025, 2, 1))
    unmatched_payment_cutoff_date = models.DateField(default=datetime.date(2025, 4, 1))
    statement_cover_letter_thresholds = models.JSONField(default=default_cover_letter_thresholds)

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
