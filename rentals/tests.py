import json
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Category, FAQ, InventoryItem, Profile, Reservation, SupportTicket


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class EventRentalTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner-test',
            password='Safe-password-123!',
        )
        self.owner_profile = Profile.objects.create(
            user=self.owner,
            role=Profile.Role.OWNER,
        )
        self.customer = User.objects.create_user(
            username='customer-test',
            password='Safe-password-123!',
        )
        Profile.objects.create(user=self.customer, role=Profile.Role.CUSTOMER)
        self.category = Category.objects.create(name='Seating')
        self.item = InventoryItem.objects.create(
            owner=self.owner,
            category=self.category,
            name='Folding chair',
            description='A sturdy event chair.',
            quantity_total=3,
            rental_price=Decimal('25.00'),
            security_deposit=Decimal('10.00'),
        )
        self.event_date = timezone.localdate() + timedelta(days=10)

    def create_reservation(self, *, quantity, start=None, end=None, status=Reservation.Status.PENDING):
        start = start or self.event_date
        end = end or start + timedelta(days=1)
        return Reservation.objects.create(
            customer=self.customer,
            item=self.item,
            quantity=quantity,
            event_date=start,
            return_date=end,
            rental_cost=Decimal('50.00'),
            security_deposit=Decimal('10.00'),
            status=status,
        )

    def test_customer_can_register_and_log_in(self):
        response = self.client.post(reverse('register'), {
            'username': 'fresh-customer',
            'email': 'fresh@example.com',
            'password1': 'An-even-safer-password-52!',
            'password2': 'An-even-safer-password-52!',
        })
        self.assertRedirects(response, reverse('dashboard'))
        self.assertTrue(Profile.objects.filter(
            user__username='fresh-customer',
            role=Profile.Role.CUSTOMER,
        ).exists())

        self.client.post(reverse('logout'))
        response = self.client.post(reverse('login'), {
            'username': 'customer-test',
            'password': 'Safe-password-123!',
        })
        self.assertRedirects(response, reverse('dashboard'))

    def test_customer_cannot_open_owner_inventory_form(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse('inventory-add'))
        self.assertRedirects(response, reverse('home'))

    def test_owner_can_create_inventory_item(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse('inventory-add'), {
            'name': 'Oak table',
            'description': 'A long event table.',
            'category': self.category.pk,
            'quantity_total': 4,
            'rental_price': '55.00',
            'security_deposit': '25.00',
            'image_url': '',
            'is_active': 'on',
        })
        self.assertRedirects(response, reverse('dashboard'))
        self.assertTrue(InventoryItem.objects.filter(owner=self.owner, name='Oak table').exists())

    def test_date_overlap_prevents_overbooking(self):
        self.create_reservation(quantity=3)
        self.client.force_login(self.customer)
        response = self.client.post(reverse('reserve-item', args=[self.item.slug]), {
            'quantity': 1,
            'event_date': self.event_date.isoformat(),
            'return_date': (self.event_date + timedelta(days=1)).isoformat(),
            'notes': '',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Only 0 item(s) are available')
        self.assertEqual(Reservation.objects.count(), 1)

    def test_non_overlapping_reservations_do_not_block_stock(self):
        self.create_reservation(quantity=3)
        other_date = self.event_date + timedelta(days=3)
        self.client.force_login(self.customer)
        response = self.client.post(reverse('reserve-item', args=[self.item.slug]), {
            'quantity': 3,
            'event_date': other_date.isoformat(),
            'return_date': (other_date + timedelta(days=1)).isoformat(),
            'notes': '',
        })
        self.assertRedirects(response, reverse('dashboard'))
        self.assertEqual(Reservation.objects.count(), 2)

    def test_reservation_cost_includes_quantity_days_and_deposit(self):
        self.client.force_login(self.customer)
        self.client.post(reverse('reserve-item', args=[self.item.slug]), {
            'quantity': 2,
            'event_date': self.event_date.isoformat(),
            'return_date': (self.event_date + timedelta(days=1)).isoformat(),
            'notes': '',
        })
        reservation = Reservation.objects.latest('id')
        self.assertEqual(reservation.rental_cost, Decimal('100.00'))
        self.assertEqual(reservation.security_deposit, Decimal('20.00'))
        self.assertEqual(reservation.total_amount, Decimal('120.00'))

    def test_owner_can_approve_their_pending_reservation(self):
        reservation = self.create_reservation(quantity=1)
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse('reservation-action', args=[reservation.pk]),
            {'action': 'approve'},
        )
        self.assertRedirects(response, reverse('dashboard'))
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.Status.APPROVED)

    def test_faq_api_returns_database_records(self):
        faq = FAQ.objects.create(question='How to reserve?', answer='Pick an item and dates.')
        response = self.client.get(reverse('api-faqs'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(faq.question, [entry['question'] for entry in response.json()['results']])

    def test_unknown_assistant_question_creates_support_ticket(self):
        response = self.client.post(
            reverse('api-chat'),
            data=json.dumps({'message': 'Can you help me arrange an unusual request?', 'session_id': ''}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['needs_human'])
        self.assertTrue(SupportTicket.objects.filter(category='Assistant escalation').exists())

    def test_assistant_uses_faq_fallback(self):
        FAQ.objects.create(
            question='How do I reserve an item?',
            answer='Choose an item and submit your dates.',
            keywords='reserve booking request',
        )
        response = self.client.post(
            reverse('api-chat'),
            data=json.dumps({'message': 'How can I reserve an item?', 'session_id': ''}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['answer'], 'Choose an item and submit your dates.')

    @override_settings(DEBUG=False)
    def test_unknown_url_renders_custom_404(self):
        response = self.client.get('/this-page-does-not-exist/')
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, 'This page wandered off.', status_code=404)
        self.assertContains(response, 'Ask the assistant', status_code=404)

    def test_health_endpoint_reports_sql_ok(self):
        response = self.client.get(reverse('health'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['dependencies']['database'], 'ok')

    @patch('rentals.views.urllib.request.urlopen', side_effect=TimeoutError)
    def test_weather_falls_back_when_provider_times_out(self, mocked_urlopen):
        response = self.client.get(reverse('api-weather'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['fallback'])
        self.assertIn('unavailable', response.json()['message'])
        mocked_urlopen.assert_called_once()

    def test_seed_command_is_repeatable_and_populates_faqs(self):
        call_command('seed_demo', stdout=StringIO())
        call_command('seed_demo', stdout=StringIO())
        self.assertEqual(InventoryItem.objects.filter(owner__username='demo_owner').count(), 14)
        self.assertGreaterEqual(FAQ.objects.filter(is_active=True).count(), 10)

    def test_authenticated_reservation_api_creates_reservation(self):
        self.client.force_login(self.customer)
        response = self.client.post(
            reverse('api-reservations'),
            data=json.dumps({
                'item_id': self.item.pk,
                'quantity': 1,
                'event_date': self.event_date.isoformat(),
                'return_date': self.event_date.isoformat(),
                'notes': 'API request',
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['rental_cost'], '25.00')
