from django.urls import path
from . import views

urlpatterns = [
    path('', views.inbox, name='inbox'),
    path('folder/<path:folder_name>/', views.inbox, name='folder_inbox'),
    path('message/<int:uid>/', views.message_detail, name='message_detail'),
    path('api/check-new-messages/', views.check_new_messages, name='check_new_messages'),
]
