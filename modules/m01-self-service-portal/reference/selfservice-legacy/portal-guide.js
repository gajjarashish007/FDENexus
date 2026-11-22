// ========== User Guide (non-technical friendly) ==========

const UserGuide = {
    initialized: false,

    init() {
        if (this.initialized) return;
        this.initialized = true;
        document.getElementById('guideSearch')?.addEventListener('input', (e) => {
            this.filterSections(e.target.value.trim().toLowerCase());
        });

        document.querySelectorAll('.guide-toc-link').forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const id = link.getAttribute('href')?.slice(1);
                this.openSection(id);
            });
        });

        document.querySelectorAll('.guide-section-toggle').forEach(btn => {
            btn.addEventListener('click', () => {
                const section = btn.closest('.guide-section');
                section?.classList.toggle('open');
            });
        });

        document.querySelectorAll('[data-goto-view]').forEach(btn => {
            btn.addEventListener('click', () => {
                const view = btn.dataset.gotoView;
                if (view && typeof switchView === 'function') switchView(view);
            });
        });

        // Open first section by default
        document.querySelector('.guide-section')?.classList.add('open');
    },

    openSection(id) {
        const el = document.getElementById(id);
        if (!el) return;
        el.classList.add('open');
        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    },

    filterSections(query) {
        document.querySelectorAll('.guide-section').forEach(section => {
            const text = section.textContent.toLowerCase();
            const match = !query || text.includes(query);
            section.hidden = !match;
            if (match && query.length > 2) section.classList.add('open');
        });

        const empty = document.getElementById('guideNoResults');
        const visible = [...document.querySelectorAll('.guide-section')].filter(s => !s.hidden).length;
        if (empty) empty.hidden = visible > 0;
    },
};
