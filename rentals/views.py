import json
import logging
import urllib.error
import urllib.request
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone as django_timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from .forms import FAQForm, InventoryItemForm, RegistrationForm, ReservationForm, SupportTicketForm
from .models import Category, ErrorCode, FAQ, InventoryItem, Profile, Reservation, SupportTicket
from .rate_limit import limited
from .services import available_quantity, customer_reservations


logger = logging.getLogger('rentals')


def is_owner(user):
    return bool(
        user.is_authenticated
        and (user.is_staff or Profile.objects.filter(user=user, role=Profile.Role.OWNER).exists())
    )


def is_customer(user):
    return bool(
        user.is_authenticated
        and Profile.objects.filter(user=user, role=Profile.Role.CUSTOMER).exists()
    )


def owner_required(view):
    from functools import wraps

    @wraps(view)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not is_owner(request.user):
            messages.error(request, 'This page is available to inventory owners only.')
            return redirect('home')
        return view(request, *args, **kwargs)

    return wrapped


def home(request):
    featured = InventoryItem.objects.filter(is_active=True).select_related('category')[:6]
    categories = Category.objects.filter(items__is_active=True).distinct()
    faqs = FAQ.objects.filter(is_active=True)[:4]
    return render(request, 'rentals/home.html', {
        'featured': featured,
        'categories': categories,
        'faqs': faqs,
    })


def inventory_list(request):
    items = InventoryItem.objects.filter(is_active=True).select_related('category')
    query = request.GET.get('q', '').strip()
    category = request.GET.get('category', '').strip()
    if query:
        items = items.filter(Q(name__icontains=query) | Q(description__icontains=query))
    if category.isdigit():
        items = items.filter(category_id=category)
    return render(request, 'rentals/inventory_list.html', {
        'items': items,
        'categories': Category.objects.filter(items__is_active=True).distinct(),
        'query': query,
        'selected_category': category,
    })


def item_detail(request, slug):
    item = get_object_or_404(
        InventoryItem.objects.select_related('category'),
        slug=slug,
        is_active=True,
    )
    return render(request, 'rentals/item_detail.html', {
        'item': item,
        'available': available_quantity(item),
    })


def register(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST' and limited(request, 'register', 5, 3600):
        return render(request, 'rentals/errors/429.html', status=429)
    form = RegistrationForm(request.POST or None)
    if form.is_valid():
        user = form.save()
        Profile.objects.create(user=user, role=Profile.Role.CUSTOMER)
        login(request, user)
        messages.success(request, 'Welcome! Your customer account is ready.')
        return redirect('dashboard')
    return render(request, 'rentals/auth_form.html', {'form': form, 'title': 'Create your account'})


def sign_in(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST' and limited(request, 'login', 8, 300):
        return render(request, 'rentals/errors/429.html', status=429)
    error = ''
    if request.method == 'POST':
        user = authenticate(
            request,
            username=request.POST.get('username', '').strip(),
            password=request.POST.get('password', ''),
        )
        if user is not None:
            login(request, user)
            next_url = request.POST.get('next', '')
            if next_url and url_has_allowed_host_and_scheme(
                next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                return redirect(next_url)
            return redirect('dashboard')
        error = 'That username and password combination was not recognized.'
    return render(request, 'rentals/auth_form.html', {
        'title': 'Welcome back',
        'error': error,
        'next': request.GET.get('next', ''),
    })


@require_POST
def sign_out(request):
    logout(request)
    messages.info(request, 'You have been signed out.')
    return redirect('home')


@login_required
def dashboard(request):
    if is_owner(request.user):
        items = InventoryItem.objects.filter(owner=request.user).select_related('category')
        reservations = Reservation.objects.filter(
            item__owner=request.user,
        ).select_related('item', 'customer').order_by('-created_at')
        tickets = SupportTicket.objects.all().select_related('customer')[:10]
        stats = {
            'inventory': items.count(),
            'available': sum(item.available_quantity() for item in items if item.is_active),
            'active': reservations.filter(status=Reservation.Status.APPROVED).count(),
            'pending': reservations.filter(status=Reservation.Status.PENDING).count(),
            'completed': reservations.filter(status=Reservation.Status.COMPLETED).count(),
            'cancelled': reservations.filter(status=Reservation.Status.CANCELLED).count(),
            'revenue': reservations.filter(
                status__in=(Reservation.Status.APPROVED, Reservation.Status.COMPLETED)
            ).aggregate(total=Sum('rental_cost'))['total'] or Decimal('0.00'),
            'tickets': SupportTicket.objects.exclude(
                status__in=(SupportTicket.Status.RESOLVED, SupportTicket.Status.CLOSED)
            ).count(),
        }
        return render(request, 'rentals/owner_dashboard.html', {
            'stats': stats,
            'items': items,
            'reservations': reservations[:25],
            'tickets': tickets,
            'status_choices': Reservation.Status.choices,
            'ticket_statuses': SupportTicket.Status.choices,
            'today': django_timezone.localdate(),
        })

    reservations = customer_reservations(request.user)
    return render(request, 'rentals/customer_dashboard.html', {
        'reservations': reservations,
        'pending': reservations.filter(status=Reservation.Status.PENDING).count(),
        'approved': reservations.filter(status=Reservation.Status.APPROVED).count(),
        'tickets': SupportTicket.objects.filter(customer=request.user)[:5],
    })


@owner_required
def inventory_manage(request, item_id=None):
    item = get_object_or_404(InventoryItem, pk=item_id, owner=request.user) if item_id else None
    form = InventoryItemForm(request.POST or None, request.FILES or None, instance=item)
    if form.is_valid():
        saved = form.save(commit=False)
        saved.owner = request.user
        saved.save()
        messages.success(request, 'Inventory item saved.')
        return redirect('dashboard')
    return render(request, 'rentals/inventory_form.html', {'form': form, 'item': item})


@owner_required
@require_POST
def inventory_deactivate(request, item_id):
    item = get_object_or_404(InventoryItem, pk=item_id, owner=request.user)
    item.is_active = False
    item.save(update_fields=('is_active', 'updated_at'))
    messages.success(request, f'{item.name} is no longer listed.')
    return redirect('dashboard')


@owner_required
@require_POST
def inventory_delete(request, item_id):
    item = get_object_or_404(InventoryItem, pk=item_id, owner=request.user)
    if Reservation.objects.filter(item=item).exists():
        item.is_active = False
        item.save(update_fields=('is_active', 'updated_at'))
        messages.warning(
            request,
            f'{item.name} has reservation history, so it was deactivated instead of deleted.',
        )
    else:
        item.delete()
        messages.success(request, 'Inventory item deleted.')
    return redirect('dashboard')


@owner_required
@require_POST
def category_create(request):
    name = request.POST.get('name', '').strip()
    if not name or len(name) > 80:
        messages.error(request, 'Category name must be between 1 and 80 characters.')
    else:
        category, created = Category.objects.get_or_create(name=name)
        messages.success(request, f'Category {category.name} {"created" if created else "already exists"}.')
    return redirect('dashboard')


@login_required
def reserve_item(request, slug):
    if not is_customer(request.user):
        messages.error(request, 'A customer account is required to request a reservation.')
        return redirect('item-detail', slug=slug)
    item = get_object_or_404(InventoryItem, slug=slug, is_active=True)
    if item.owner_id == request.user.id:
        messages.error(request, 'You cannot reserve your own inventory.')
        return redirect('item-detail', slug=slug)
    form = ReservationForm(request.POST or None)
    if form.is_valid():
        reservation = None
        with transaction.atomic():
            locked_item = get_object_or_404(
                InventoryItem.objects.select_for_update(),
                pk=item.pk,
                is_active=True,
            )
            data = form.cleaned_data
            available = available_quantity(locked_item, data['event_date'], data['return_date'])
            if data['quantity'] > available:
                form.add_error('quantity', f'Only {available} item(s) are available for those dates.')
            else:
                days = (data['return_date'] - data['event_date']).days + 1
                reservation = form.save(commit=False)
                reservation.customer = request.user
                reservation.item = locked_item
                reservation.rental_cost = (
                    locked_item.rental_price * data['quantity'] * days
                ).quantize(Decimal('0.01'))
                reservation.security_deposit = locked_item.security_deposit * data['quantity']
                reservation.save()
        if reservation:
            messages.success(request, 'Reservation request sent to the owner for approval.')
            return redirect('dashboard')
    return render(request, 'rentals/reservation_form.html', {'form': form, 'item': item})


@login_required
@require_POST
def reservation_action(request, reservation_id):
    reservation = get_object_or_404(
        Reservation.objects.select_related('item'),
        pk=reservation_id,
    )
    owner_action = is_owner(request.user) and reservation.item.owner_id == request.user.id
    customer_action = reservation.customer_id == request.user.id
    action = request.POST.get('action')
    if owner_action and reservation.status == Reservation.Status.PENDING:
        if action == 'approve':
            reservation.status = Reservation.Status.APPROVED
        elif action == 'reject':
            reservation.status = Reservation.Status.REJECTED
        else:
            messages.error(request, 'That reservation action is not available.')
            return redirect('dashboard')
    elif (
        owner_action
        and reservation.status == Reservation.Status.APPROVED
        and action == 'complete'
        and reservation.return_date < django_timezone.localdate()
    ):
        reservation.status = Reservation.Status.COMPLETED
    elif customer_action and action == 'cancel' and reservation.status in (
        Reservation.Status.PENDING,
        Reservation.Status.APPROVED,
    ):
        if reservation.event_date <= django_timezone.localdate():
            messages.error(request, 'Reservations can only be cancelled before the event date.')
            return redirect('dashboard')
        reservation.status = Reservation.Status.CANCELLED
    else:
        messages.error(request, 'You do not have permission to change this reservation.')
        return redirect('dashboard')
    reservation.save(update_fields=('status', 'updated_at'))
    messages.success(request, 'Reservation status updated.')
    return redirect('dashboard')


def faq_page(request):
    return render(request, 'rentals/faqs.html', {
        'faqs': FAQ.objects.filter(is_active=True),
        'owner': is_owner(request.user),
    })


@owner_required
def faq_manage(request, faq_id=None):
    faq = get_object_or_404(FAQ, pk=faq_id) if faq_id else None
    if request.method == 'POST':
        form = FAQForm(request.POST, instance=faq)
        if form.is_valid():
            form.save()
            messages.success(request, 'FAQ saved.')
            return redirect('faq-page')
    else:
        form = FAQForm(instance=faq)
    return render(request, 'rentals/faq_form.html', {'form': form, 'faq': faq})


@owner_required
@require_POST
def faq_delete(request, faq_id):
    get_object_or_404(FAQ, pk=faq_id).delete()
    messages.success(request, 'FAQ deleted.')
    return redirect('faq-page')


@login_required
def support_page(request):
    form = SupportTicketForm(request.POST or None)
    if request.method == 'POST':
        if limited(request, 'ticket', 5, 3600):
            return render(request, 'rentals/errors/429.html', status=429)
        if form.is_valid():
            ticket = form.save(commit=False)
            ticket.customer = request.user
            ticket.save()
            messages.success(request, f'Support ticket #{ticket.pk} was created.')
            return redirect('support')
    tickets = SupportTicket.objects.all() if is_owner(request.user) else SupportTicket.objects.filter(customer=request.user)
    return render(request, 'rentals/support.html', {
        'form': form,
        'tickets': tickets.select_related('customer')[:50],
        'owner': is_owner(request.user),
        'status_choices': SupportTicket.Status.choices,
    })


@owner_required
@require_POST
def ticket_action(request, ticket_id):
    ticket = get_object_or_404(SupportTicket, pk=ticket_id)
    status = request.POST.get('status')
    if status not in SupportTicket.Status.values:
        messages.error(request, 'Select a valid ticket status.')
    else:
        ticket.status = status
        ticket.save(update_fields=('status', 'updated_at'))
        messages.success(request, 'Support ticket updated.')
    return redirect('support')


@require_POST
def support_ticket_api(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Sign in to create a support ticket.'}, status=401)
    if limited(request, 'ticket-api', 5, 3600):
        return JsonResponse({'error': 'Too many support requests. Please try again later.'}, status=429)
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Send a valid JSON object.'}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({'error': 'Send a valid JSON object.'}, status=400)
    data = dict(payload)
    data.setdefault('category', 'General')
    data.setdefault('priority', SupportTicket.Priority.MEDIUM)
    form = SupportTicketForm(data)
    if not form.is_valid():
        return JsonResponse({'errors': form.errors.get_json_data()}, status=400)
    ticket = form.save(commit=False)
    ticket.customer = request.user
    ticket.save()
    return JsonResponse({'id': ticket.pk, 'status': ticket.status}, status=201)


def about(request):
    return render(request, 'rentals/about.html')


@require_GET
def health(request):
    from django.db import DatabaseError, connections
    from pymongo.errors import PyMongoError

    checks = {'database': 'ok', 'mongodb': 'not_configured' if not settings.MONGODB_URI else 'unavailable'}
    healthy = True
    try:
        connections['default'].ensure_connection()
    except DatabaseError:
        logger.exception('Health check could not connect to SQL.')
        checks['database'] = 'unavailable'
        healthy = False
    if settings.MONGODB_URI:
        try:
            from pymongo import MongoClient

            with MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=1500) as client:
                client.admin.command('ping')
            checks['mongodb'] = 'ok'
        except (PyMongoError, ValueError):
            logger.exception('Health check could not connect to MongoDB.')
            healthy = False
    return JsonResponse(
        {'status': 'healthy' if healthy else 'degraded', 'dependencies': checks},
        status=200 if healthy else 503,
    )


@require_GET
def inventory_api(request, slug=None):
    items = InventoryItem.objects.filter(is_active=True).select_related('category')
    if slug:
        items = items.filter(slug=slug)
    return JsonResponse({'results': [{
        'id': item.pk,
        'name': item.name,
        'slug': item.slug,
        'category': item.category.name if item.category else 'Other',
        'description': item.description,
        'rental_price': str(item.rental_price),
        'security_deposit': str(item.security_deposit),
        'available_quantity': item.available_quantity(),
        'image': item.image.url if item.image else item.image_url,
    } for item in items[:100]]})


@require_GET
def faq_api(request):
    return JsonResponse({'results': list(FAQ.objects.filter(is_active=True).values('id', 'question', 'answer'))})


def reservation_api(request):
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Sign in to view or request reservations.'}, status=401)
    if request.method == 'GET':
        reservations = Reservation.objects.select_related('item')
        if is_owner(request.user):
            reservations = reservations.filter(item__owner=request.user)
        else:
            reservations = reservations.filter(customer=request.user)
        return JsonResponse({'results': [{
            'id': reservation.pk,
            'item': reservation.item.name,
            'quantity': reservation.quantity,
            'event_date': reservation.event_date.isoformat(),
            'return_date': reservation.return_date.isoformat(),
            'rental_cost': str(reservation.rental_cost),
            'security_deposit': str(reservation.security_deposit),
            'status': reservation.status,
        } for reservation in reservations[:100]]})
    if limited(request, 'reservation-api', 10, 60):
        return JsonResponse({'error': 'Please wait a moment before requesting another reservation.'}, status=429)
    if not is_customer(request.user):
        return JsonResponse({'error': 'A customer account is required to request a reservation.'}, status=403)
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Send a valid JSON object.'}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({'error': 'Send a valid JSON object.'}, status=400)
    item_id = payload.get('item_id')
    if isinstance(item_id, bool) or not str(item_id).isdigit():
        return JsonResponse({'error': 'Provide a valid item_id.'}, status=400)
    item = get_object_or_404(InventoryItem, pk=int(item_id), is_active=True)
    if item.owner_id == request.user.pk:
        return JsonResponse({'error': 'You cannot reserve your own inventory.'}, status=403)
    form = ReservationForm(payload)
    if not form.is_valid():
        return JsonResponse({'errors': form.errors.get_json_data()}, status=400)
    with transaction.atomic():
        locked_item = get_object_or_404(InventoryItem.objects.select_for_update(), pk=item.pk, is_active=True)
        data = form.cleaned_data
        available = available_quantity(locked_item, data['event_date'], data['return_date'])
        if data['quantity'] > available:
            return JsonResponse({
                'error': f'Only {available} item(s) are available for those dates.',
                'code': 'EVT-001',
            }, status=409)
        days = (data['return_date'] - data['event_date']).days + 1
        reservation = form.save(commit=False)
        reservation.customer = request.user
        reservation.item = locked_item
        reservation.rental_cost = (locked_item.rental_price * data['quantity'] * days).quantize(Decimal('0.01'))
        reservation.security_deposit = locked_item.security_deposit * data['quantity']
        reservation.save()
    return JsonResponse({
        'id': reservation.pk,
        'status': reservation.status,
        'rental_cost': str(reservation.rental_cost),
        'security_deposit': str(reservation.security_deposit),
        'total_amount': str(reservation.total_amount),
    }, status=201)


@require_GET
def weather_api(request):
    url = 'https://api.open-meteo.com/v1/forecast?latitude=12.9716&longitude=77.5946&current=temperature_2m,weather_code&timezone=Asia%2FKolkata'
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            data = json.loads(response.read().decode('utf-8'))
        return JsonResponse({
            'location': 'Bengaluru',
            'temperature_c': data['current']['temperature_2m'],
            'weather_code': data['current']['weather_code'],
            'fallback': False,
        })
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError):
        logger.warning('Weather provider unavailable; returning friendly fallback.', exc_info=True)
        return JsonResponse({
            'location': 'Bengaluru',
            'message': 'Weather information is currently unavailable.',
            'fallback': True,
        }, status=200)


def bad_request(request, exception=None):
    return render(request, 'rentals/errors/400.html', status=400)


def permission_denied(request, exception=None):
    return render(request, 'rentals/errors/403.html', status=403)


def page_not_found(request, exception=None):
    return render(request, 'rentals/errors/404.html', status=404)


def server_error(request):
    return render(request, 'rentals/errors/500.html', status=500)
