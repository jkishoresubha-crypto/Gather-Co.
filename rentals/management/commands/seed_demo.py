from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from rentals.models import (
    Category,
    ErrorCode,
    FAQ,
    InventoryItem,
    Profile,
    Reservation,
    SupportTicket,
)


FAQS = [
    (
        'How do I reserve an item?',
        'Choose an item, select your dates and quantity, then send a reservation request. The owner will review it and update its status in your dashboard.',
        'reserve booking request',
    ),
    (
        'How can I check item availability?',
        'Open an item page and start a reservation with your event and return dates. Availability is checked against existing reservations for those dates.',
        'availability stock dates',
    ),
    (
        'Can I reserve multiple items?',
        'You can create a separate reservation request for each item. Each request is checked against that item’s available quantity.',
        'multiple items quantity',
    ),
    (
        'How is the rental cost calculated?',
        'Rental cost is the item’s daily price multiplied by the requested quantity and the number of rental days. The security deposit is shown separately.',
        'price cost total',
    ),
    (
        'Is a security deposit required?',
        'Some items have a security deposit. The item page shows the deposit per item, and the reservation summary includes the total deposit.',
        'deposit security',
    ),
    (
        'Can I cancel my reservation?',
        'You can cancel a pending or approved reservation from your dashboard before its event date. Contact support if your event is today or has passed.',
        'cancel cancellation',
    ),
    (
        'How do I contact support?',
        'Sign in and open Support to create a ticket. You can also ask Gather assistant to help and it will create a ticket if it cannot answer.',
        'support ticket contact',
    ),
    (
        'What happens if an item is unavailable?',
        'The reservation form will show the number available for your selected dates. You can choose a smaller quantity or different dates.',
        'unavailable stock quantity',
    ),
    (
        'Can I change my reservation?',
        'Please create a support ticket with your reservation details. The owner can review your request and help update the plan.',
        'change edit update reservation',
    ),
    (
        'How long does approval take?',
        'The inventory owner reviews each request. You can check the current status any time from your customer dashboard.',
        'approval pending status',
    ),
    (
        'When is the rental period counted?',
        'The event date and return date are both included in the rental period for pricing and availability.',
        'duration return days',
    ),
    (
        'Do I need an account to reserve?',
        'You need a customer account to request reservations and see their status. Registration is free.',
        'account login register',
    ),
]

CATEGORIES = {
    'Seating': 'Chairs and stools for every kind of gathering.',
    'Tables': 'Dining, display, and cocktail tables.',
    'Lighting': 'Warm light to set the mood.',
    'Audio': 'Sound essentials for speeches and celebrations.',
    'Stage & AV': 'Stages and equipment for the main moment.',
    'Tents': 'Shelter and shade for outdoor events.',
    'Decor': 'Finishing touches for a personal setting.',
}

ITEMS = [
    ('Folding Event Chairs', 'Seating', 'Lightweight, sturdy chairs for ceremonies and receptions.', 80, '35.00', '100.00'),
    ('Oak Crossback Chairs', 'Seating', 'Warm oak-finish chairs that bring a natural touch to the table.', 36, '180.00', '300.00'),
    ('Round Banquet Table', 'Tables', 'A generous round table for shared meals and conversation.', 18, '450.00', '500.00'),
    ('Farmhouse Dining Table', 'Tables', 'A handcrafted-look table for a relaxed, welcoming setting.', 10, '850.00', '1000.00'),
    ('Cocktail High Table', 'Tables', 'A compact standing table for drinks and mingling.', 20, '280.00', '300.00'),
    ('Warm String Lights', 'Lighting', 'Soft ambient lights to bring a little glow to the evening.', 24, '220.00', '250.00'),
    ('LED Uplight Set', 'Lighting', 'Color-adjustable uplights for walls, stages, and dance floors.', 14, '600.00', '800.00'),
    ('Portable PA Speaker', 'Audio', 'A clear, portable speaker for announcements and music.', 8, '900.00', '1500.00'),
    ('Wireless Microphone', 'Audio', 'A wireless microphone for toasts, talks, and performances.', 12, '350.00', '500.00'),
    ('Modular Stage Deck', 'Stage & AV', 'Flexible stage platform sections for a focal point or performance.', 12, '1200.00', '2000.00'),
    ('HD Event Projector', 'Stage & AV', 'Bright projection for slides, photos, and special moments.', 5, '1500.00', '2500.00'),
    ('Garden Marquee Tent', 'Tents', 'A spacious canopy for an outdoor celebration.', 4, '4500.00', '8000.00'),
    ('Ceremony Arch', 'Decor', 'A simple event arch ready for flowers and fabric.', 6, '1100.00', '1800.00'),
    ('Tabletop Bud Vases', 'Decor', 'A set of clear glass vases for an easy floral finish.', 50, '45.00', '100.00'),
]


class Command(BaseCommand):
    help = 'Create repeatable demo accounts, inventory, FAQs, reservations, and tickets.'

    def handle(self, *args, **options):
        owner, owner_created = User.objects.get_or_create(
            username='demo_owner',
            defaults={'email': 'owner@example.com'},
        )
        if owner_created:
            owner.set_password('Owner@12345')
            owner.save()
        else:
            if owner.is_staff:
                owner.is_staff = False
                owner.save(update_fields=['is_staff'])
        Profile.objects.update_or_create(user=owner, defaults={'role': Profile.Role.OWNER})

        customer, customer_created = User.objects.get_or_create(
            username='demo_customer',
            defaults={'email': 'customer@example.com'},
        )
        if customer_created:
            customer.set_password('Customer@12345')
            customer.save()
        Profile.objects.update_or_create(user=customer, defaults={'role': Profile.Role.CUSTOMER})

        categories = {}
        for name, description in CATEGORIES.items():
            categories[name], _ = Category.objects.get_or_create(
                name=name,
                defaults={'description': description},
            )

        for name, category, description, quantity, price, deposit in ITEMS:
            InventoryItem.objects.get_or_create(
                slug=name.lower().replace(' ', '-').replace('&', 'and'),
                defaults={
                    'owner': owner,
                    'category': categories[category],
                    'name': name,
                    'description': description,
                    'quantity_total': quantity,
                    'rental_price': Decimal(price),
                    'security_deposit': Decimal(deposit),
                },
            )

        for question, answer, keywords in FAQS:
            FAQ.objects.get_or_create(
                question=question,
                defaults={'answer': answer, 'keywords': keywords, 'is_active': True},
            )

        error_codes = [
            ('400', 'Bad request', 'The submitted information could not be understood.', 'Check the form fields and try again.'),
            ('401', 'Sign in required', 'This action requires an authenticated account.', 'Sign in and try again.'),
            ('403', 'Access restricted', 'Your account does not have permission for this action.', 'Contact an administrator if you need access.'),
            ('404', 'Page not found', 'We could not find the page you requested.', 'Browse the collection or return home.'),
            ('429', 'Too many requests', 'Requests are temporarily rate limited.', 'Wait a moment and try again.'),
            ('500', 'Something went wrong', 'An unexpected issue prevented this request.', 'Try again later.'),
            ('503', 'Service unavailable', 'A service is temporarily unavailable.', 'Please try again shortly.'),
            ('EVT-001', 'Inventory unavailable', 'The requested quantity is not available for those dates.', 'Choose fewer items or different dates.'),
        ]
        for code, title, explanation, resolution in error_codes:
            ErrorCode.objects.get_or_create(
                code=code,
                defaults={'title': title, 'explanation': explanation, 'resolution': resolution},
            )

        first_item = InventoryItem.objects.get(name='Folding Event Chairs', owner=owner)
        future = timezone.localdate() + timedelta(days=14)
        Reservation.objects.get_or_create(
            customer=customer,
            item=first_item,
            event_date=future,
            defaults={
                'quantity': 8,
                'return_date': future + timedelta(days=1),
                'rental_cost': Decimal('560.00'),
                'security_deposit': Decimal('800.00'),
                'status': Reservation.Status.PENDING,
                'notes': 'Demo birthday gathering',
            },
        )
        SupportTicket.objects.get_or_create(
            customer=customer,
            subject='Demo: delivery timing question',
            defaults={
                'description': 'Could you confirm the usual delivery window for an approved reservation?',
                'category': 'Delivery',
                'priority': SupportTicket.Priority.LOW,
            },
        )

        self.stdout.write(self.style.SUCCESS(
            'Demo data is ready. Existing passwords were not changed.'
        ))
