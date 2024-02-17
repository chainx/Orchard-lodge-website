from django import forms
from .models import resident, payment, invoice

class UploadFileForm(forms.ModelForm):
    class Meta:
        model = invoice
        fields = ['filename']
        labels = {'filename': 'Please upload invoices here'}
        # widgets = {'filename': forms.ClearableFileInput(attrs={'multiple': True})}

class ResidentForm(forms.ModelForm):
    class Meta:
        model = resident
        fields = ['title', 'first', 'last', 'current', 'private', 'private_rate', 'filters']
        widgets = {
            'title' : forms.TextInput(attrs={'placeholder': 'Title', 'style': 'width: 70px;'}),
            'first' : forms.TextInput(attrs={'placeholder': 'First', 'style': 'width: 200px;'}),
            'last' : forms.TextInput(attrs={'placeholder': 'Last', 'style': 'width: 200px;'}),
            'private_rate' : forms.TextInput(attrs={'placeholder': 'Private rate', 'style': 'width: 100px;'}),
            'filters' : forms.TextInput(attrs={'placeholder': 'Filters', 'style': 'width: 500px;'})
        }

    def is_valid(self):
        valid = super(ResidentForm, self).is_valid()
        return valid

class MatchPayment(forms.Form):
    ID = forms.IntegerField(label='Invoice ID',required=False)

class InvoiceForm(forms.ModelForm):
    class Meta:
        model = invoice
        fields = ['Payment']