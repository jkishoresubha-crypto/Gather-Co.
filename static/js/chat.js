document.addEventListener('DOMContentLoaded', () => {
    const form = document.querySelector('#chat-form');
    const panel = document.querySelector('#chat-panel');
    const launcher = document.querySelector('#chat-launcher');
    const closeButton = document.querySelector('#chat-close');
    const clearButton = document.querySelector('#chat-clear');
    const messages = document.querySelector('#chat-messages');
    const status = document.querySelector('#chat-status');
    const input = document.querySelector('#chat-input');
    if (!form || !panel || !launcher || !messages || !input || !status) return;

    const sessionKey = 'gather-chat-session';
    let sessionId = localStorage.getItem(sessionKey) || '';
    const cookieToken = () => form.querySelector('input[name="csrfmiddlewaretoken"]')?.value || '';

    const togglePanel = (open) => {
        panel.hidden = !open;
        launcher.setAttribute('aria-expanded', String(open));
        if (open) input.focus();
    };
    launcher.addEventListener('click', () => togglePanel(panel.hidden));
    closeButton?.addEventListener('click', () => togglePanel(false));
    clearButton?.addEventListener('click', () => {
        sessionId = '';
        localStorage.removeItem(sessionKey);
        messages.replaceChildren();
        const welcome = document.createElement('p');
        welcome.className = 'chat-bubble assistant-bubble';
        welcome.textContent = 'New conversation. How can I help with your event?';
        messages.append(welcome);
        status.textContent = '';
    });

    const addBubble = (text, className) => {
        const bubble = document.createElement('p');
        bubble.className = `chat-bubble ${className}`;
        bubble.textContent = text;
        messages.append(bubble);
        messages.scrollTop = messages.scrollHeight;
        return bubble;
    };

    const addFeedback = (session) => {
        const controls = document.createElement('div');
        controls.className = 'chat-feedback';
        [['Helpful', 1], ['Not helpful', -1]].forEach(([label, rating]) => {
            const button = document.createElement('button');
            button.type = 'button';
            button.textContent = label;
            button.addEventListener('click', async () => {
                button.disabled = true;
                try {
                    await fetch(form.dataset.feedbackUrl, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': cookieToken() },
                        body: JSON.stringify({ rating, session_id: session }),
                    });
                    status.textContent = 'Thanks for your feedback.';
                } catch {
                    status.textContent = 'Feedback could not be sent right now.';
                }
            });
            controls.append(button);
        });
        messages.append(controls);
    };

    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        const message = input.value.trim();
        if (!message) return;
        addBubble(message, 'user-bubble');
        input.value = '';
        status.textContent = '';
        const loading = addBubble('Gather is thinking…', 'assistant-bubble chat-loading');
        const submitButton = form.querySelector('button[type="submit"]');
        if (submitButton) submitButton.disabled = true;
        try {
            const response = await fetch(form.dataset.url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': cookieToken() },
                body: JSON.stringify({ message, session_id: sessionId }),
            });
            const data = await response.json();
            loading.remove();
            if (!response.ok) throw new Error(data.error || 'The assistant is unavailable. Please try again.');
            sessionId = data.session_id;
            localStorage.setItem(sessionKey, sessionId);
            addBubble(data.answer, 'assistant-bubble');
            addFeedback(sessionId);
            if (data.ticket_id) status.textContent = `Support ticket #${data.ticket_id} created.`;
        } catch (error) {
            loading.remove();
            addBubble(error.message || 'The assistant is unavailable. Please try again.', 'assistant-bubble');
        } finally {
            if (submitButton) submitButton.disabled = false;
            input.focus();
        }
    });
});
