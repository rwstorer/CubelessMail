from django.urls import path
from . import views

urlpatterns = [
    path('', views.inbox, name='inbox'),
    path('folder/<path:folder_name>/', views.inbox, name='folder_inbox'),
    path('message/<int:uid>/', views.message_detail, name='message_detail'),
    path('message/<int:uid>/fragment/', views.message_detail_fragment, name='message_detail_fragment'),
    path('message/<int:uid>/inline/<int:part_index>/', views.inline_image, name='inline_image'),
    path('message/<int:uid>/attachment/<int:part_index>/', views.download_attachment, name='download_attachment'),
    path('folders/create/', views.create_folder, name='create_folder'),
    path('folders/delete/', views.delete_folder, name='delete_folder'),
    path('api/check-new-messages/', views.check_new_messages, name='check_new_messages'),
]
