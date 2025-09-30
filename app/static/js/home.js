(function() {
    // IntersectionObserver to reveal elements
    const els = document.querySelectorAll('.reveal');
    if (!('IntersectionObserver' in window) || els.length === 0) {
        els.forEach(el => el.classList.add('in'));
        return;
    }

    const io = new IntersectionObserver((entries) => {
        entries.forEach((e) => {
            if (e.isIntersecting) {
                const delay = parseInt(e.target.getAttribute('data-delay') || '0', 10);
                if (delay) e.target.style.transitionDelay = `${delay}ms`;
                e.target.classList.add('in');
                io.unobserve(e.target);
            }
        });
    }, { threshold: 0.12, rootMargin: '0px 0px -5% 0px' });

    els.forEach(el => io.observe(el));
})();