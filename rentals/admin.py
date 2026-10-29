from django.contrib import admin

from .models import Category, ErrorCode, FAQ, InventoryItem, Profile, Reservation, SupportTicket


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'owner', 'quantity_total', 'rental_price', 'is_active')
    list_filter = ('is_active', 'category')
    search_fields = ('name', 'description', 'owner__username')


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ('id', 'item', 'customer', 'quantity', 'event_date', 'return_date', 'status')
    list_filter = ('status', 'event_date')
    search_fields = ('item__name', 'customer__username')


admin.site.register((Category, FAQ, Profile, SupportTicket, ErrorCode))
