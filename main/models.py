from django.db import models
from django.core.validators import MinLengthValidator

class resident(models.Model):
    title = models.CharField(max_length=8)
    first = models.CharField(max_length=32)
    last = models.CharField(max_length=32)
    current = models.BooleanField(default=False)
    private = models.BooleanField(default=False)
    private_rate = models.IntegerField(default=0,blank=True, null=True)
    filters = models.CharField(max_length=256,default='',blank=True, null=True)

    @property
    def name(self):
        if self.title=='':
            return f'{self.first} {self.last}'
        return f'{self.title} {self.first} {self.last}'
    
    @property
    def url(self):
        return self.name.replace(' ','-')

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
    bank='Bank'
    expected='Expected'
    type_choices = [(cash,cash),(cheque,cheque),(bank,bank),(expected,expected)]
    type = models.CharField(max_length=8, choices=type_choices, blank=True, null=True)


    @property
    def str_amount(self):
        return u'\u00A3' + f'{self.amount/100:.2f}'

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