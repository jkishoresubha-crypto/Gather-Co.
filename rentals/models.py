from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.text import slugify


class Profile(models.Model):
    class Role(models.TextChoices):
        OWNER = 'owner', 'Owner'
        CUSTOMER = 'customer', 'Customer'

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.CUSTOMER)

    def __str__(self):
        return f'{self.user.username} ({self.role})'


class Category(models.Model):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=90, unique=True, blank=True)
    description = models.CharField(max_length=240, blank=True)

    class Meta:
        ordering = ('name',)
        verbose_name_plural = 'categories'

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class InventoryItem(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='inventory_items',
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name='items',
        null=True,
        blank=True,
    )
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    description = models.TextField()
    image = models.ImageField(upload_to='inventory/', blank=True)
    image_url = models.URLField(blank=True)
    quantity_total = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    rental_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    security_deposit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('name',)
        indexes = [models.Index(fields=('is_active', 'category'))]

    def save(self, *args, **kwargs):
        if not self.slug:
            root = slugify(self.name) or 'item'
            candidate = root
            suffix = 2
            while InventoryItem.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                candidate = f'{root}-{suffix}'
                suffix += 1
            self.slug = candidate
        super().save(*args, **kwargs)

    def available_quantity(self, start_date=None, end_date=None):
        from .services import available_quantity

        return available_quantity(self, start_date, end_date)

    def __str__(self):
        return self.name


class Reservation(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'
        CANCELLED = 'cancelled', 'Cancelled'
        COMPLETED = 'completed', 'Completed'

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reservations',
    )
    item = models.ForeignKey(
        InventoryItem,
        on_delete=models.PROTECT,
        related_name='reservations',
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    event_date = models.DateField()
    return_date = models.DateField()
    rental_cost = models.DecimalField(max_digits=12, decimal_places=2)
    security_deposit = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created_at',)
        indexes = [
            models.Index(fields=('item', 'status', 'event_date', 'return_date')),
            models.Index(fields=('customer', 'status')),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(return_date__gte=models.F('event_date')),
                name='reservation_return_after_event',
            ),
            models.CheckConstraint(condition=models.Q(quantity__gte=1), name='reservation_qty_positive'),
        ]

    @property
    def duration_days(self):
        return (self.return_date - self.event_date).days + 1

    @property
    def total_amount(self):
        return self.rental_cost + self.security_deposit

    def __str__(self):
        return f'{self.item.name} reservation #{self.pk}'


class FAQ(models.Model):
    question = models.CharField(max_length=255)
    answer = models.TextField()
    keywords = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ('question',)

    def __str__(self):
        return self.question


class SupportTicket(models.Model):
    class Status(models.TextChoices):
        OPEN = 'open', 'Open'
        IN_PROGRESS = 'in_progress', 'In progress'
        RESOLVED = 'resolved', 'Resolved'
        CLOSED = 'closed', 'Closed'

    class Priority(models.TextChoices):
        LOW = 'low', 'Low'
        MEDIUM = 'medium', 'Medium'
        HIGH = 'high', 'High'
        CRITICAL = 'critical', 'Critical'

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='support_tickets',
        null=True,
        blank=True,
    )
    subject = models.CharField(max_length=120)
    description = models.TextField()
    category = models.CharField(max_length=60, default='General')
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f'Ticket #{self.pk}: {self.subject}'


class ErrorCode(models.Model):
    code = models.CharField(max_length=12, unique=True)
    title = models.CharField(max_length=120)
    explanation = models.TextField()
    resolution = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ('code',)

    def __str__(self):
        return f'{self.code}: {self.title}'
