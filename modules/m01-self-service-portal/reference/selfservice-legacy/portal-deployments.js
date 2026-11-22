// ========== Manage Deployments View (table layout) ==========

const ManageDeployments = {
    deployments: [],
    filterStatus: '',
    filterSearch: '',

    async init() {
        document.getElementById('refreshDeploymentsBtn')?.addEventListener('click', () => this.load());
        document.getElementById('deploySearch')?.addEventListener('input', (e) => {
            this.filterSearch = e.target.value.toLowerCase();
            this.render();
        });
        document.getElementById('deployStatusFilter')?.addEventListener('change', (e) => {
            this.filterStatus = e.target.value;
            this.render();
        });
        document.getElementById('newDeployBtn')?.addEventListener('click', () => switchView('servicesView'));
        document.getElementById('closeEditDeployModal')?.addEventListener('click', () => this.hideEditModal());
        document.querySelector('.edit-deploy-backdrop')?.addEventListener('click', () => this.hideEditModal());
        document.getElementById('saveEditDeployBtn')?.addEventListener('click', () => this.saveEditRerun());
    },

    async load() {
        const tbody = document.getElementById('deploymentsTableBody');
        if (!tbody) return;
        tbody.innerHTML = '<tr><td colspan="6" class="deploy-loading">Loading deployments...</td></tr>';

        try {
            const res = await fetch(`${window.location.origin}/api/deploy/deployments`);
            const data = await res.json();
            this.deployments = data.deployments || [];
            this.render();
        } catch (err) {
            tbody.innerHTML = `<tr><td colspan="6" class="deploy-empty">Failed to load: ${err.message}</td></tr>`;
        }
    },

    formatDate(iso) {
        if (!iso) return '—';
        return new Date(iso).toLocaleString();
    },

    shortId(id) {
        if (!id) return '—';
        return id.length > 12 ? `${id.slice(0, 8)}…` : id;
    },

    render() {
        const tbody = document.getElementById('deploymentsTableBody');
        const countEl = document.getElementById('deploymentsCount');
        if (!tbody) return;

        let filtered = this.deployments;
        if (this.filterStatus) {
            filtered = filtered.filter(d => d.status === this.filterStatus);
        }
        if (this.filterSearch) {
            filtered = filtered.filter(d =>
                (d.id || '').toLowerCase().includes(this.filterSearch) ||
                (d.resourceName || '').toLowerCase().includes(this.filterSearch) ||
                (d.serviceType || '').toLowerCase().includes(this.filterSearch)
            );
        }

        if (countEl) countEl.textContent = `${filtered.length} deployment${filtered.length !== 1 ? 's' : ''}`;

        if (filtered.length === 0) {
            tbody.innerHTML = `
                <tr><td colspan="6" class="deploy-empty">
                    <p>No deployments found</p>
                    <button class="btn-table-action btn-rerun" onclick="switchView('servicesView')">+ Create Deployment</button>
                </td></tr>`;
            return;
        }

        tbody.innerHTML = filtered.map(d => this.renderRow(d)).join('');
        this.bindRowActions();
    },

    renderRow(d) {
        const isError = d.status === 'ERROR';
        const statusClass = isError ? 'status-error' : d.status === 'APPLIED' ? 'status-applied' : 'status-pending';
        const name = d.resourceName || d.appName || '—';
        const urlCell = d.url
            ? `<a href="${d.url}" target="_blank" class="deploy-table-link">${d.url.replace(/^https?:\/\//, '')}</a>`
            : '<span class="deploy-table-muted">—</span>';

        const actions = isError ? `
            <button class="btn-table-action btn-edit" data-action="edit" data-id="${d.id}" title="Edit &amp; Rerun">✏️</button>
            <button class="btn-table-action btn-delete-ws" data-action="delete-ws" data-id="${d.id}" title="Delete Workspace">🗑</button>
        ` : `
            <button class="btn-table-action btn-rerun" data-action="rerun" data-id="${d.id}" title="Rerun">↻</button>
            <button class="btn-table-action btn-edit" data-action="edit" data-id="${d.id}" title="Edit &amp; Rerun">✏️</button>
            <button class="btn-table-action btn-destroy" data-action="destroy" data-id="${d.id}" title="Destroy &amp; Delete">✕</button>
        `;

        const detailRow = `
            <tr class="deploy-detail-row" data-detail-for="${d.id}" hidden>
                <td colspan="6">
                    <div class="deploy-detail-inner">
                        <span><strong>ID:</strong> <code>${d.id}</code></span>
                        <span><strong>Created:</strong> ${this.formatDate(d.createdAt)}</span>
                        ${d.containerPort ? `<span><strong>Port:</strong> ${d.containerPort}</span>` : ''}
                        ${d.platform ? `<span><strong>Platform:</strong> ${d.platform}</span>` : ''}
                        ${d.errorMessage ? `<span class="deploy-detail-error">⚠ ${d.errorMessage}</span>` : ''}
                    </div>
                </td>
            </tr>`;

        return `
            <tr class="deploy-table-row ${isError ? 'deploy-row-error' : ''}" data-id="${d.id}">
                <td>
                    <button type="button" class="deploy-row-toggle" data-toggle-id="${d.id}" title="Show details">▸</button>
                    <strong class="deploy-table-name">${name}</strong>
                </td>
                <td>${d.serviceType || d.type}</td>
                <td><span class="deploy-status ${statusClass}">${d.status}</span></td>
                <td>${urlCell}</td>
                <td class="deploy-table-date">${this.formatDate(d.updatedAt)}</td>
                <td><div class="deploy-table-actions">${actions}</div></td>
            </tr>
            ${detailRow}
        `;
    },

    bindRowActions() {
        document.querySelectorAll('.deploy-row-toggle').forEach(btn => {
            btn.addEventListener('click', () => {
                const id = btn.dataset.toggleId;
                const detail = document.querySelector(`[data-detail-for="${id}"]`);
                const open = detail && detail.hidden;
                document.querySelectorAll('.deploy-detail-row').forEach(r => { r.hidden = true; });
                document.querySelectorAll('.deploy-row-toggle').forEach(b => { b.textContent = '▸'; });
                if (open && detail) {
                    detail.hidden = false;
                    btn.textContent = '▾';
                }
            });
        });

        document.querySelectorAll('[data-action]').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                const id = btn.dataset.id;
                const action = btn.dataset.action;
                if (action === 'rerun') await this.rerun(id);
                else if (action === 'edit') this.openEditModal(id);
                else if (action === 'destroy') await this.destroy(id);
                else if (action === 'delete-ws') await this.deleteWorkspace(id);
            });
        });
    },

    async rerun(id) {
        try {
            const res = await fetch(`${window.location.origin}/api/deploy/deployments/${id}/rerun`, { method: 'POST' });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error);
            showToast(data.message, 'success');
            await this.load();
        } catch (err) {
            showToast(err.message, 'error');
        }
    },

    openEditModal(id) {
        const dep = this.deployments.find(d => d.id === id);
        if (!dep) return;
        document.getElementById('editDeployId').value = id;
        document.getElementById('editResourceName').value = dep.resourceName || dep.appName || '';
        document.getElementById('editContainerPort').value = dep.containerPort || 80;
        document.getElementById('editPlatform').value = dep.platform || 'linux/amd64';
        document.getElementById('editDeployModal').classList.add('show');
    },

    hideEditModal() {
        document.getElementById('editDeployModal')?.classList.remove('show');
    },

    async saveEditRerun() {
        const id = document.getElementById('editDeployId').value;
        const resourceName = document.getElementById('editResourceName').value.trim().toLowerCase();
        const containerPort = parseInt(document.getElementById('editContainerPort').value, 10);
        const platform = document.getElementById('editPlatform').value;

        if (typeof FormValidation !== 'undefined') {
            const err = FormValidation.firstError(
                FormValidation.validateAppName(resourceName),
                FormValidation.validatePort(containerPort, 'Container port'),
            );
            if (err) {
                showToast(err, 'error');
                return;
            }
        } else if (!resourceName || containerPort < 1 || containerPort > 65535) {
            showToast('Please enter a valid name and port (1–65535)', 'error');
            return;
        }

        const body = { resourceName, containerPort, platform };
        try {
            const res = await fetch(`${window.location.origin}/api/deploy/deployments/${id}/edit-rerun`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error);
            showToast(data.message, 'success');
            this.hideEditModal();
            await this.load();
        } catch (err) {
            showToast(err.message, 'error');
        }
    },

    async destroy(id) {
        const dep = this.deployments.find(d => d.id === id);
        if (!confirm(`Destroy and delete deployment "${dep?.resourceName || id}"? This cannot be undone.`)) return;
        try {
            const res = await fetch(`${window.location.origin}/api/deploy/deployments/${id}`, { method: 'DELETE' });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error);
            showToast(data.message, 'success');
            await this.load();
        } catch (err) {
            showToast(err.message, 'error');
        }
    },

    async deleteWorkspace(id) {
        if (!confirm('Delete this failed workspace and all associated resources?')) return;
        try {
            const res = await fetch(`${window.location.origin}/api/deploy/deployments/${id}/delete-workspace`, { method: 'POST' });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error);
            showToast(data.message, 'success');
            await this.load();
        } catch (err) {
            showToast(err.message, 'error');
        }
    },
};
