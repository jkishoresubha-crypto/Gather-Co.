from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from .models import Reservation


ACTIVE_STATUSES = (Reservation.Status.PENDING, Reservation.Status.APPROVED)


def reserved_peak(item, start_date, end_date):
    reservations = Reservation.objects.filter(
        item=item,
        status__in=ACTIVE_STATUSES,
        event_date__lte=end_date,
        return_date__gte=start_date,
    ).values_list('event_date', 'return_date', 'quantity')
    changes = {}
    for reserved_start, reserved_end, quantity in reservations:
        first_day = max(start_date, reserved_start)
        day_after_last = min(end_date, reserved_end) + timedelta(days=1)
        changes[first_day] = changes.get(first_day, 0) + quantity
        changes[day_after_last] = changes.get(day_after_last, 0) - quantity
    running = peak = 0
    for day in sorted(changes):
        running += changes[day]
        peak = max(peak, running)
    return peak


def available_quantity(item, start_date=None, end_date=None):
    if start_date is None or end_date is None:
        today = timezone.localdate()
        start_date = today
        end_date = today
    return max(item.quantity_total - reserved_peak(item, start_date, end_date), 0)


def customer_reservations(user):
    return Reservation.objects.filter(customer=user).select_related('item', 'item__category')
