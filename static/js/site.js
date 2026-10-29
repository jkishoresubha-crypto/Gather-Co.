document.addEventListener('DOMContentLoaded', () => {
    const menuButton = document.querySelector('.menu-toggle');
    const navigation = document.querySelector('#main-nav');
    if (menuButton && navigation) {
        menuButton.addEventListener('click', () => {
            const expanded = menuButton.getAttribute('aria-expanded') === 'true';
            menuButton.setAttribute('aria-expanded', String(!expanded));
            navigation.classList.toggle('is-open', !expanded);
        });
    }

    document.querySelectorAll('[data-open-chat]').forEach((button) => {
        button.addEventListener('click', () => document.querySelector('#chat-launcher')?.click());
    });

    const weatherCard = document.querySelector('#weather-card');
    const weatherReading = document.querySelector('#weather-reading');
    if (weatherCard && weatherReading) {
        fetch(weatherCard.dataset.weatherUrl)
            .then((response) => response.json())
            .then((data) => {
                weatherReading.textContent = data.fallback
                    ? data.message
                    : `Bengaluru today: ${data.temperature_c}°C`;
            })
            .catch(() => {
                weatherReading.textContent = 'Weather information is currently unavailable.';
            });
    }
});
