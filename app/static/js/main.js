document.addEventListener('DOMContentLoaded', () => {
    // Mobile menu toggle with icon animation
    const btn = document.getElementById('mobile-menu-button');
    const menu = document.getElementById('mobile-menu');
    const iconOpen = document.getElementById('menu-icon-open');
    const iconClose = document.getElementById('menu-icon-close');

    if(btn && menu) {
        btn.addEventListener('click', () => {
            const isHidden = menu.classList.contains('hidden');
            menu.classList.toggle('hidden');
            
            // Animate hamburger <-> X icon
            if(iconOpen && iconClose) {
                if(isHidden) {
                    iconOpen.classList.add('opacity-0', 'scale-50');
                    iconClose.classList.remove('opacity-0', 'scale-50');
                } else {
                    iconOpen.classList.remove('opacity-0', 'scale-50');
                    iconClose.classList.add('opacity-0', 'scale-50');
                }
            }
        });
    }

    // Smooth scroll for anchor links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            const targetId = this.getAttribute('href');
            if(targetId === '#') return;
            
            const targetElement = document.querySelector(targetId);
            if(targetElement) {
                e.preventDefault();
                targetElement.scrollIntoView({
                    behavior: 'smooth'
                });
                
                // Close mobile menu if open
                if(menu && !menu.classList.contains('hidden')) {
                    menu.classList.add('hidden');
                    if(iconOpen && iconClose) {
                        iconOpen.classList.remove('opacity-0', 'scale-50');
                        iconClose.classList.add('opacity-0', 'scale-50');
                    }
                }
            }
        });
    });

    // Navbar shrink on scroll
    const nav = document.getElementById('main-nav');
    if(nav) {
        window.addEventListener('scroll', () => {
            if(window.scrollY > 20) {
                nav.classList.add('is-scrolled');
            } else {
                nav.classList.remove('is-scrolled');
            }
        });
    }

    // Intersection Observer for fade-in animations
    const observerOptions = {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if(entry.isIntersecting) {
                entry.target.classList.add('fade-in-up');
                observer.unobserve(entry.target);
            }
        });
    }, observerOptions);

    document.querySelectorAll('section').forEach(section => {
        section.style.opacity = '0';
        observer.observe(section);
    });

    // Don't fade the hero (first section)
    const firstSection = document.querySelector('main > section:first-child');
    if(firstSection) {
        firstSection.style.opacity = '1';
        observer.unobserve(firstSection);
    }
});
