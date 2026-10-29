from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone

from .models import FAQ, InventoryItem, Reservation, SupportTicket


class RegistrationForm(UserCreationForm):
    email = forms.EmailField()

    class Meta:
        model = User
        fields = ('username', 'email')


class InventoryItemForm(forms.ModelForm):
    class Meta:
        model = InventoryItem
        fields = (
            'name', 'category', 'description', 'image', 'image_url',
            'quantity_total', 'rental_price', 'security_deposit', 'is_active',
        )
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'quantity_total': forms.NumberInput(attrs={'min': 1}),
            'rental_price': forms.NumberInput(attrs={'min': '0.01', 'step': '0.01'}),
            'security_deposit': forms.NumberInput(attrs={'min': '0', 'step': '0.01'}),
        }


class ReservationForm(forms.ModelForm):
    class Meta:
        model = Reservation
        fields = ('quantity', 'event_date', 'return_date', 'notes')
        widgets = {
            'event_date': forms.DateInput(attrs={'type': 'date'}),
            'return_date': forms.DateInput(attrs={'type': 'date'}),
            'quantity': forms.NumberInput(attrs={'min': 1}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

    def clean_event_date(self):
        event_date = self.cleaned_data['event_date']
        if event_date < timezone.localdate():
            raise forms.ValidationError('Select today or a future date.')
        return event_date

    def clean(self):
        cleaned_data = super().clean()
        event_date = cleaned_data.get('event_date')
        return_date = cleaned_data.get('return_date')
        if event_date and return_date and return_date < event_date:
            self.add_error('return_date', 'Return date must be on or after the event date.')
        return cleaned_data


class SupportTicketForm(forms.ModelForm):
    class Meta:
        model = SupportTicket
        fields = ('subject', 'description', 'category', 'priority')
        widgets = {'description': forms.Textarea(attrs={'rows': 5})}


class FAQForm(forms.ModelForm):
    class Meta:
        model = FAQ
        fields = ('question', 'answer', 'keywords', 'is_active')
