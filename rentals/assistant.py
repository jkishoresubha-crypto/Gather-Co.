import json
import logging
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from uuid import uuid4

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from .models import ErrorCode, FAQ, SupportTicket
from .rate_limit import limited


logger = logging.getLogger('rentals')
STOP_WORDS = {'a', 'an', 'and', 'can', 'do', 'for', 'how', 'i', 'in', 'is', 'it', 'me', 'my', 'of', 'the', 'to', 'what', 'when', 'where', 'with', 'you'}


def faq_match(message):
    words = {
        word for word in re.findall(r'[a-z0-9]+', message.lower())
        if len(word) > 2 and word not in STOP_WORDS
    }
    if not words:
        return None
    best = None
    best_score = 0
    for faq in FAQ.objects.filter(is_active=True):
        faq_words = {
            word for word in re.findall(r'[a-z0-9]+', f'{faq.question} {faq.keywords}'.lower())
            if len(word) > 2 and word not in STOP_WORDS
        }
        score = len(words & faq_words) / len(words)
        if score > best_score:
            best, best_score = faq, score
    return best if best_score >= 0.3 else None


def ai_answer(message, faqs):
    if not settings.AI_API_KEY:
        return None
    context = '\n'.join(f'Q: {faq.question}\nA: {faq.answer}' for faq in faqs[:20])
    payload = json.dumps({
        'model': settings.AI_MODEL,
        'messages': [
            {
                'role': 'system',
                'content': (
                    'You are Gather, a concise event-rental support assistant. '
                    'Answer using this FAQ context only. If it is insufficient, '
                    'respond with the exact marker NEED_HUMAN. '
                    'Do not guess at policy or availability.\n' + context
                ),
            },
            {'role': 'user', 'content': message},
        ],
        'temperature': 0.2,
    }).encode('utf-8')
    request = urllib.request.Request(
        settings.AI_API_URL,
        data=payload,
        headers={
            'Authorization': f'Bearer {settings.AI_API_KEY}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            result = json.loads(response.read().decode('utf-8'))
        answer = result['choices'][0]['message']['content'].strip()
        return None if not answer or 'NEED_HUMAN' in answer else answer
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError, IndexError):
        logger.warning('AI provider unavailable; falling back to FAQ matching.', exc_info=True)
        return None


def save_chat_log(session_id, message, response, user_id=None, feedback=None):
    if not settings.MONGODB_URI:
        return None
    try:
        with MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=1500) as client:
            database = client[settings.MONGODB_DATABASE]
            result = database.chat_logs.insert_one({
                'user_id': user_id,
                'session_id': session_id,
                'message': message[:1000],
                'response': response[:2000],
                'timestamp': datetime.now(timezone.utc),
                'feedback': feedback,
            })
        return str(result.inserted_id)
    except (PyMongoError, ValueError):
        logger.exception('Could not save chat interaction to MongoDB.')
        return None


@require_POST
def chat_api(request):
    if limited(request, 'assistant', 12, 60):
        return JsonResponse({'error': 'You are sending messages quickly. Please wait a moment.'}, status=429)
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Send a valid JSON message.'}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({'error': 'Send a JSON object.'}, status=400)
    message = payload.get('message')
    if not isinstance(message, str) or not message.strip() or len(message) > 1000:
        return JsonResponse({'error': 'Message must contain 1 to 1000 characters.'}, status=400)
    message = message.strip()
    session_id = payload.get('session_id')
    if not isinstance(session_id, str) or len(session_id) > 100:
        return JsonResponse({'error': 'Invalid chat session.'}, status=400)
    session_id = session_id or str(uuid4())

    active_faqs = list(FAQ.objects.filter(is_active=True))
    faq = faq_match(message)
    error_match = re.search(r'\b(?:EVT-\d{3}|(?:400|401|403|404|429|500|503))\b', message.upper())
    error = ErrorCode.objects.filter(code__iexact=error_match.group(0), is_active=True).first() if error_match else None
    answer = None
    if error:
        answer = f'{error.code}: {error.title}. {error.explanation} {error.resolution}'.strip()
    if not answer:
        answer = ai_answer(message, active_faqs)
    if not answer and faq:
        answer = faq.answer
    ticket = None
    if not answer:
        ticket = SupportTicket.objects.create(
            customer=request.user if request.user.is_authenticated else None,
            subject=message[:120],
            description=(
                f'Assistant could not confidently answer this question:\n\n{message}'
            ),
            category='Assistant escalation',
            priority=SupportTicket.Priority.MEDIUM,
        )
        answer = (
            f'I could not find a confident answer, so I created support ticket '
            f'#{ticket.pk}. Our team can help you with this.'
        )

    log_id = save_chat_log(
        session_id,
        message,
        answer,
        request.user.pk if request.user.is_authenticated else None,
    )
    return JsonResponse({
        'answer': answer,
        'session_id': session_id,
        'ticket_id': ticket.pk if ticket else None,
        'log_id': log_id,
        'needs_human': ticket is not None,
    })


@require_POST
def feedback_api(request):
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Send a valid JSON message.'}, status=400)
    if not isinstance(payload, dict) or payload.get('rating') not in (1, -1):
        return JsonResponse({'error': 'Feedback rating must be 1 or -1.'}, status=400)
    comment = payload.get('comment', '')
    session_id = payload.get('session_id', '')
    if not isinstance(comment, str) or len(comment) > 500:
        return JsonResponse({'error': 'Feedback must be 500 characters or fewer.'}, status=400)
    if not isinstance(session_id, str) or len(session_id) > 100:
        return JsonResponse({'error': 'Invalid chat session.'}, status=400)
    if not settings.MONGODB_URI:
        return JsonResponse({'error': 'Feedback storage is not configured.'}, status=503)
    try:
        with MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=1500) as client:
            client[settings.MONGODB_DATABASE].feedback.insert_one({
                'rating': payload['rating'],
                'comment': comment.strip(),
                'session_id': session_id,
                'timestamp': datetime.now(timezone.utc),
                'user_id': request.user.pk if request.user.is_authenticated else None,
            })
    except PyMongoError:
        logger.exception('Could not save assistant feedback to MongoDB.')
        return JsonResponse({'error': 'Feedback could not be saved right now.'}, status=503)
    return JsonResponse({'saved': True})
