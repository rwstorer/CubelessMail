from django.contrib import admin
from .models import EmailAccount


@admin.register(EmailAccount)
class EmailAccountAdmin(admin.ModelAdmin):
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
