// ========== Admin User Approvals ==========

const AdminUsers = {
    pendingUsers: [],

    init() {
        document.getElementById('refreshPendingBtn')?.addEventListener('click', () => this.load());
    },

    async load() {
        const list = document.getElementById('pendingUsersList');
        if (!list) return;
        list.innerHTML = '<div class="deploy-loading">Loading pending requests...</div>';

        try {
            const res = await Auth.apiFetch('/auth/pending-users');
            const data = await res.json();
            this.pendingUsers = data.users || [];
            this.render();
            this.updateBadge();
        } catch (err) {
            list.innerHTML = `<div class="deploy-empty">${err.message}</div>`;
        }
    },

    updateBadge() {
        const badge = document.getElementById('pendingBadge');
        const count = this.pendingUsers.length;
        if (!badge) return;
        if (count > 0) {
            badge.textContent = count;
            badge.hidden = false;
        } else {
            badge.hidden = true;
        }
    },

    formatDate(iso) {
        if (!iso) return '—';
        return new Date(iso).toLocaleString();
    },

    render() {
        const list = document.getElementById('pendingUsersList');
        const countEl = document.getElementById('pendingCount');
        if (!list) return;

        if (countEl) {
            countEl.textContent = `${this.pendingUsers.length} pending request${this.pendingUsers.length !== 1 ? 's' : ''}`;
        }

        if (this.pendingUsers.length === 0) {
            list.innerHTML = '<div class="deploy-empty">No pending signup requests</div>';
            return;
        }

        list.innerHTML = this.pendingUsers.map(u => `
            <div class="pending-user-card">
                <div class="pending-user-main">
                    <div class="pending-user-name">${u.username}</div>
                    <div class="pending-user-email">${u.email}</div>
                    <div class="pending-user-meta">Requested ${this.formatDate(u.created_at)}</div>
                </div>
                <div class="pending-user-actions">
                    <button class="btn-deploy-action btn-approve" data-action="approve" data-id="${u.id}">✓ Approve</button>
                    <button class="btn-deploy-action btn-reject" data-action="reject" data-id="${u.id}">✕ Reject</button>
                </div>
            </div>
        `).join('');

        list.querySelectorAll('[data-action]').forEach(btn => {
            btn.addEventListener('click', async () => {
                const id = btn.dataset.id;
                const action = btn.dataset.action;
                if (action === 'approve') await this.approve(id);
                else if (action === 'reject') await this.reject(id);
            });
        });
    },

    async approve(id) {
        const user = this.pendingUsers.find(u => String(u.id) === String(id));
        if (!confirm(`Approve access for "${user?.username}"?`)) return;
        try {
            const res = await Auth.apiFetch(`/auth/users/${id}/approve`, { method: 'POST' });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error);
            showToast(data.message, 'success');
            await this.load();
        } catch (err) {
            showToast(err.message, 'error');
        }
    },

    async reject(id) {
        const user = this.pendingUsers.find(u => String(u.id) === String(id));
        if (!confirm(`Reject signup request for "${user?.username}"?`)) return;
        try {
            const res = await Auth.apiFetch(`/auth/users/${id}/reject`, { method: 'POST' });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error);
            showToast(data.message, 'success');
            await this.load();
        } catch (err) {
            showToast(err.message, 'error');
        }
    },
};
