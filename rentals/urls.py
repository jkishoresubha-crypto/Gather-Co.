from django.urls import path

from . import views
from . import assistant

urlpatterns = [
    path('', views.home, name='home'),
    path('inventory/', views.inventory_list, name='inventory-list'),
    path('inventory/<slug:slug>/', views.item_detail, name='item-detail'),
    path('inventory/<slug:slug>/reserve/', views.reserve_item, name='reserve-item'),
    path('accounts/register/', views.register, name='register'),
    path('accounts/login/', views.sign_in, name='login'),
    path('accounts/logout/', views.sign_out, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('owner/inventory/add/', views.inventory_manage, name='inventory-add'),
    path('owner/inventory/<int:item_id>/edit/', views.inventory_manage, name='inventory-edit'),
    path('owner/inventory/<int:item_id>/deactivate/', views.inventory_deactivate, name='inventory-deactivate'),
    path('owner/inventory/<int:item_id>/delete/', views.inventory_delete, name='inventory-delete'),
    path('owner/categories/add/', views.category_create, name='category-add'),
    path('reservations/<int:reservation_id>/action/', views.reservation_action, name='reservation-action'),
    path('faqs/', views.faq_page, name='faq-page'),
    path('owner/faqs/add/', views.faq_manage, name='faq-add'),
    path('owner/faqs/<int:faq_id>/edit/', views.faq_manage, name='faq-edit'),
    path('owner/faqs/<int:faq_id>/delete/', views.faq_delete, name='faq-delete'),
    path('support/', views.support_page, name='support'),
    path('owner/tickets/<int:ticket_id>/status/', views.ticket_action, name='ticket-action'),
    path('about/', views.about, name='about'),
    path('health/', views.health, name='health'),
    path('api/inventory/', views.inventory_api, name='api-inventory'),
    path('api/inventory/<slug:slug>/', views.inventory_api, name='api-item'),
    path('api/faqs/', views.faq_api, name='api-faqs'),
    path('api/reservations/', views.reservation_api, name='api-reservations'),
    path('api/support/tickets/', views.support_ticket_api, name='api-support-tickets'),
    path('api/chat/', assistant.chat_api, name='api-chat'),
    path('api/feedback/', assistant.feedback_api, name='api-feedback'),
    path('api/weather/', views.weather_api, name='api-weather'),
]
