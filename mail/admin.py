from django.contrib import admin
from django import forms
from .models import EmailAccount


class EmailAccountAdminForm(forms.ModelForm):
    """Custom form to handle password encryption."""
    imap_password = forms.CharField(
        label='IMAP Password',
        required=False,
        widget=forms.PasswordInput(),
        help_text='Enter the password. Leave blank to keep the existing password.'
    )

    class Meta:
        model = EmailAccount
        fields = ('email', 'imap_host', 'imap_port', 'imap_username', 'imap_password')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Don't require password on update
        if self.instance.pk:
            self.fields['imap_password'].required = False

    def save(self, commit=True):
        instance = super().save(commit=False)
        # If a new password was entered, encrypt and set it
        if self.cleaned_data.get('imap_password'):
            instance.set_imap_password(self.cleaned_data['imap_password'])
        if commit:
            instance.save()
        return instance


@admin.register(EmailAccount)
class EmailAccountAdmin(admin.ModelAdmin):
    form = EmailAccountAdminForm
    list_display = ('email', 'imap_host', 'created_at')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Email Address', {
            'fields': ('email',)
        }),
        ('IMAP Configuration', {
            'fields': ('imap_host', 'imap_port', 'imap_username', 'imap_password')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
