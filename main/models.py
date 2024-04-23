from django.db import models
from django.core.validators import MinLengthValidator

class resident(models.Model):
    title = models.CharField(max_length=8)
    first = models.CharField(max_length=32)
    last = models.CharField(max_length=32)
    sefton_id = models.CharField(max_length=32, blank=True, null=True)
    current = models.BooleanField(default=False)
    private = models.BooleanField(default=False)
    private_rate = models.IntegerField(default=0, blank=True, null=True)
    filters = models.CharField(max_length=256, default='', blank=True, null=True)
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
        return sum([invoice_.total for invoice_ in self.invoice_set.filter(obsolete=False)])
    def total_payed(self):
        return sum([payment_.amount for payment_ in self.payment_set.all()])
    def total_owed(self):
        return self.total_invoiced() - self.total_payed()
    def len_invoices(self):
        return len(self.invoice_set.filter(obsolete=False))
    def len_payments(self):
        return len(self.payment_set.all())

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
    santander='Santander'
    rbs='RBS'
    type_choices = [(cash,cash),(cheque,cheque),(santander, santander),(rbs, rbs)]
    type = models.CharField(max_length=9, choices=type_choices, blank=True, null=True)


    @property
    def str_amount(self):
        return u'\u00A3' + f'{self.amount/100:.2f}'
    
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
        return u'\u00A3' + f'{self.total/100:.2f}'

    def __str__(self):
        return str(self.filename)
    
class sefton_login_details(models.Model):
    email = models.CharField(max_length=256, blank=True, null=True)
    password = models.CharField(max_length=256, blank=True, null=True)
    passcode = models.CharField(max_length=6, blank=True, null=True)