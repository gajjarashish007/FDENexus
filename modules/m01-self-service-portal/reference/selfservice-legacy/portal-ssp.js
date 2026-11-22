const SSP = {
    chatHistory: [],
    planReviewed: false,
    planDestructive: false,
    diffConfirmed: false,
    prApproved: false,
    currentMessage: '',
    currentStep: 1,
    typingEl: null,

    async init() {
        await this.loadDropdowns();
        this.bindEvents();
        this.setupWebSocketHandlers();
        await this.loadPRStatus();
        this.setWorkflowStep(1);
    },

    setWorkflowStep(step) {
        this.currentStep = step;
        document.querySelectorAll('.workflow-stepper .step').forEach(el => {
            const s = parseInt(el.dataset.step, 10);
            el.classList.remove('active', 'done');
            if (s < step) el.classList.add('done');
            else if (s === step) el.classList.add('active');
        });
    },

    switchSspTab(tab) {
        document.querySelectorAll('.ssp-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
        document.querySelectorAll('.ssp-tab-panel').forEach(p => p.classList.toggle('active', p.dataset.panel === tab));
    },

    async loadDropdowns() {
        try {
            const [svcRes, accRes] = await Promise.all([
                Auth.apiFetch('/middleware/services'),
                Auth.apiFetch('/middleware/accounts'),
            ]);
            const svcData = await svcRes.json();
            const accData = await accRes.json();

            const svcSelect = document.getElementById('serviceSelect');
            svcSelect.innerHTML = svcData.services.map(s =>
                `<option value="${s.id}">${s.icon} ${s.name}</option>`
            ).join('');

            const accSelect = document.getElementById('accountSelect');
            accSelect.innerHTML = accData.accounts.map(a =>
                `<option value="${a.id}">${a.name} (${a.accountId})</option>`
            ).join('');
        } catch (err) {
            showToast('Failed to load middleware data: ' + err.message, 'error');
        }
    },

    bindEvents() {
        document.getElementById('sendChatBtn').addEventListener('click', () => this.sendMessage());
        document.getElementById('chatInput').addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && e.ctrlKey) {
                e.preventDefault();
                this.sendMessage();
            }
            if (e.key === 'Escape') {
                e.target.value = '';
            }
        });
        document.getElementById('clearChatBtn').addEventListener('click', () => this.clearChat());
        document.getElementById('confirmDiffBtn').addEventListener('click', () => this.confirmDiff());
        document.getElementById('rejectDiffBtn').addEventListener('click', () => this.rejectDiff());
        document.getElementById('applyBtn').addEventListener('click', () => this.applyChanges());
        document.getElementById('approvePrBtn').addEventListener('click', () => this.approvePR());
        document.getElementById('copyPlanBtn').addEventListener('click', () => this.copyOutput('planOutput'));
        document.getElementById('copyApplyBtn').addEventListener('click', () => this.copyOutput('applyOutput'));
        document.getElementById('copyYamlBeforeBtn').addEventListener('click', () => this.copyYaml('before'));
        document.getElementById('copyYamlAfterBtn').addEventListener('click', () => this.copyYaml('after'));
        document.getElementById('helpChatBtn').addEventListener('click', () => switchView('helpView'));

        document.querySelectorAll('.quick-chip').forEach(chip => {
            chip.addEventListener('click', () => {
                document.getElementById('chatInput').value = chip.dataset.msg;
                this.sendMessage();
            });
        });

        document.querySelectorAll('.ssp-tab').forEach(tab => {
            tab.addEventListener('click', () => this.switchSspTab(tab.dataset.tab));
        });

        document.getElementById('serviceSelect').addEventListener('change', () => {
            this.setWorkflowStep(1);
            this.loadPRStatus();
        });
        document.getElementById('accountSelect').addEventListener('change', () => {
            this.setWorkflowStep(1);
            this.loadPRStatus();
        });
        document.getElementById('regionSelect').addEventListener('change', async (e) => {
            const region = e.target.value;
            try {
                const res = await Auth.apiFetch('/region', {
                    method: 'POST',
                    body: JSON.stringify({ region }),
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.error || 'Failed to set region');
                showToast(`AWS region set to ${data.region || region}`, 'success');
            } catch (err) {
                showToast(err.message, 'error');
            }
        });
    },

    formatAssistantMessage(text) {
        return text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/`([^`]+)`/g, '<code>$1</code>')
            .replace(/\n/g, '<br>');
    },

    yamlFilePath(service, account, suffix) {
        return `infra/${account}/${service}/${service}-${account}-resource.yaml`;
    },

    copyOutput(elementId) {
        const el = document.getElementById(elementId);
        const text = el.innerText || el.textContent;
        if (!text.trim()) {
            showToast('Nothing to copy', 'info');
            return;
        }
        navigator.clipboard.writeText(text).then(() => showToast('Copied to clipboard!', 'success'));
    },

    copyYaml(which) {
        const el = document.getElementById(which === 'before' ? 'yamlBefore' : 'yamlAfter');
        const text = el.textContent;
        if (!text.trim()) {
            showToast('Nothing to copy', 'info');
            return;
        }
        navigator.clipboard.writeText(text).then(() => showToast('YAML copied!', 'success'));
    },

    hideWelcome() {
        const welcome = document.getElementById('chatWelcome');
        if (welcome) welcome.remove();
    },

    showTypingIndicator() {
        this.hideTypingIndicator();
        const container = document.getElementById('chatMessages');
        const el = document.createElement('div');
        el.className = 'chat-msg assistant typing-indicator';
        el.innerHTML = '<span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-label">Analyzing request…</span>';
        container.appendChild(el);
        container.scrollTop = container.scrollHeight;
        this.typingEl = el;
    },

    hideTypingIndicator() {
        if (this.typingEl) {
            this.typingEl.remove();
            this.typingEl = null;
        }
    },

    setupWebSocketHandlers() {
        WSClient.on('plan', (data) => this.handlePlanOutput(data));
        WSClient.on('apply', (data) => this.handleApplyOutput(data));
        WSClient.on('error', (data) => showToast(data.message || 'WebSocket error', 'error'));
    },

    getService() {
        return document.getElementById('serviceSelect').value;
    },

    getAccount() {
        return document.getElementById('accountSelect').value;
    },

    highlightYaml(el, text) {
        el.textContent = text;
        el.className = 'language-yaml';
        el.removeAttribute('data-highlighted');
        if (typeof hljs !== 'undefined') {
            hljs.highlightElement(el);
        }
    },

    renderDiffSummary(diff) {
        const summaryEl = document.getElementById('diffSummary');
        const titleEl = document.getElementById('diffSummaryTitle');
        const listEl = document.getElementById('diffSummaryList');

        if (!diff.changes || diff.changes.length === 0) {
            summaryEl.hidden = true;
            return;
        }

        titleEl.textContent = diff.summary || 'Configuration changes';
        listEl.innerHTML = diff.changes.map(ch => {
            const cls = ch.type === 'destroy' ? 'change-destroy' : ch.type === 'add' ? 'change-add' : 'change-modify';
            const icon = ch.type === 'destroy' ? '⚠' : ch.type === 'add' ? '+' : '~';
            return `<li class="${cls}"><span class="change-icon">${icon}</span> ${ch.detail}</li>`;
        }).join('');
        summaryEl.hidden = false;
    },

    async sendMessage() {
        const input = document.getElementById('chatInput');
        const message = input.value.trim();
        if (!message) return;
        if (message.length > 2000) {
            showToast('Message is too long (max 2000 characters)', 'error');
            return;
        }

        this.currentMessage = message;
        input.value = '';
        this.resetWorkflow();
        this.hideWelcome();
        this.setWorkflowStep(2);
        this.switchSspTab('workflow');

        this.addChatMessage('user', message);
        document.getElementById('sendChatBtn').disabled = true;
        this.showTypingIndicator();

        try {
            const service = this.getService();
            const account = this.getAccount();

            const res = await fetch(`${API_BASE}/chat/stream`, {
                method: 'POST',
                headers: Auth.authHeaders(),
                body: JSON.stringify({
                    message,
                    service,
                    account,
                    history: this.chatHistory,
                }),
            });

            if (!res.ok) throw new Error('Chat request failed');

            this.hideTypingIndicator();
            const msgEl = this.addChatMessage('assistant', '', true);
            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let fullText = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                const chunk = decoder.decode(value, { stream: true });
                fullText += chunk;
                msgEl.innerHTML = this.formatAssistantMessage(fullText);
                msgEl.scrollIntoView({ behavior: 'smooth', block: 'end' });
            }

            msgEl.classList.remove('streaming');
            this.chatHistory.push({ role: 'user', content: message });
            this.chatHistory.push({ role: 'assistant', content: fullText });

            this.addChatMessage('system', '📄 Generating YAML diff for your review…');
            await this.loadYamlDiff(message);
            this.setWorkflowStep(3);
            if (typeof refreshLogsIfVisible === 'function') refreshLogsIfVisible();
        } catch (err) {
            this.hideTypingIndicator();
            this.addChatMessage('system', 'Error: ' + err.message);
            showToast(err.message, 'error');
        } finally {
            document.getElementById('sendChatBtn').disabled = false;
        }
    },

    addChatMessage(role, text, streaming = false) {
        const container = document.getElementById('chatMessages');
        const el = document.createElement('div');
        el.className = `chat-msg ${role}${streaming ? ' streaming' : ''}`;
        if (role === 'assistant') {
            el.innerHTML = this.formatAssistantMessage(text);
        } else {
            el.textContent = text;
        }
        container.appendChild(el);
        container.scrollTop = container.scrollHeight;
        return el;
    },

    clearChat() {
        document.getElementById('chatMessages').innerHTML = `
            <div class="chat-welcome" id="chatWelcome">
                <h4>👋 Getting Started</h4>
                <p>Follow these simple steps:</p>
                <ol>
                    <li>Pick a <strong>Service</strong> and <strong>Account</strong> above</li>
                    <li>Click a <strong>Quick action</strong> or type your request</li>
                    <li>Review the YAML diff and plan on the right</li>
                    <li>Approve the PR and click <strong>Apply</strong></li>
                </ol>
            </div>`;
        this.chatHistory = [];
        this.resetWorkflow();
        this.setWorkflowStep(1);
    },

    async loadYamlDiff(message) {
        try {
            const service = this.getService();
            const account = this.getAccount();
            const res = await Auth.apiFetch('/plan/yaml-diff', {
                method: 'POST',
                body: JSON.stringify({ service, account, message }),
            });
            const diff = await res.json();

            const beforeEl = document.getElementById('yamlBefore');
            const afterEl = document.getElementById('yamlAfter');
            this.highlightYaml(beforeEl, diff.before);
            this.highlightYaml(afterEl, diff.after);

            document.getElementById('yamlBeforePath').textContent =
                this.yamlFilePath(service, account, 'before');
            document.getElementById('yamlAfterPath').textContent =
                this.yamlFilePath(service, account, 'after');

            this.renderDiffSummary(diff);

            const section = document.getElementById('yamlDiffSection');
            section.hidden = false;

            const badge = document.getElementById('diffBadge');
            if (diff.destructive) {
                badge.textContent = '⚠ Destructive Change';
                badge.className = 'badge badge-danger';
            } else {
                badge.textContent = 'Pending Review';
                badge.className = 'badge badge-info';
            }

            this.planDestructive = diff.destructive;
            this.diffConfirmed = false;
            this.updateApplyButton();

            this.addChatMessage('system',
                diff.destructive
                    ? '⚠ YAML diff ready — contains destructive changes. Review carefully before confirming.'
                    : '✓ YAML diff ready — review Before/After on the right, then Confirm to generate the Terraform plan.'
            );
        } catch (err) {
            showToast('Failed to load YAML diff: ' + err.message, 'error');
        }
    },

    async recordWorkflowLog(action, details) {
        try {
            await Auth.apiFetch('/logs/record', {
                method: 'POST',
                body: JSON.stringify({
                    action,
                    service: this.getService(),
                    account: this.getAccount(),
                    message: details || this.currentMessage,
                }),
            });
            if (typeof refreshLogsIfVisible === 'function') refreshLogsIfVisible();
        } catch (err) {
            console.warn('Failed to record workflow log:', err);
        }
    },

    confirmDiff() {
        this.diffConfirmed = true;
        document.getElementById('yamlDiffSection').querySelector('.diff-actions').hidden = true;
        document.getElementById('diffBadge').textContent = '✓ Confirmed';
        document.getElementById('diffBadge').className = 'badge badge-approved';

        this.addChatMessage('system', '✓ YAML diff confirmed. Generating Terraform plan…');
        this.recordWorkflowLog('yaml_diff_confirmed', this.currentMessage);
        this.setWorkflowStep(4);
        this.startPlanGeneration();
    },

    rejectDiff() {
        document.getElementById('yamlDiffSection').hidden = true;
        document.getElementById('diffSummary').hidden = true;
        this.diffConfirmed = false;
        this.planReviewed = false;
        this.updateApplyButton();
        this.addChatMessage('system', 'YAML diff rejected. Modify your request and try again.');
        this.recordWorkflowLog('yaml_diff_rejected', this.currentMessage);
    },

    startPlanGeneration() {
        const planOutput = document.getElementById('planOutput');
        planOutput.innerHTML = '';
        document.getElementById('planStatus').textContent = 'Generating...';
        document.getElementById('planStatus').className = 'badge badge-warn';

        this.planReviewed = false;
        this.updateApplyButton();

        WSClient.generatePlan(this.getService(), this.getAccount(), this.currentMessage)
            .catch(err => showToast(err.message, 'error'));
    },

    classifyPlanLine(line) {
        if (!line) return '';
        if (/destroy|DESTRUCTIVE|WARNING/i.test(line)) return 'line-destroy';
        if (line.startsWith('Plan:')) return 'line-summary';
        if (/^\[\d/.test(line)) return 'line-timestamp';
        if (line.startsWith('  +')) return 'line-add';
        if (line.startsWith('  ~')) return 'line-change';
        if (line.startsWith('  -')) return 'line-remove';
        if (line.startsWith('  #')) return 'line-comment';
        if (line.startsWith('Terraform will')) return 'line-header';
        return '';
    },

    handlePlanOutput(data) {
        const planOutput = document.getElementById('planOutput');

        if (data.type === 'plan_line') {
            const line = document.createElement('div');
            line.textContent = data.line;
            const cls = this.classifyPlanLine(data.line);
            if (cls) line.className = cls;
            planOutput.appendChild(line);
            planOutput.scrollTop = planOutput.scrollHeight;
        }

        if (data.type === 'plan_complete') {
            this.planDestructive = data.destructive;
            this.planReviewed = true;

            const statusEl = document.getElementById('planStatus');
            if (data.destructive) {
                statusEl.textContent = '⚠ Destructive';
                statusEl.className = 'badge badge-danger';
                this.addChatMessage('system', '⚠ Plan contains DESTRUCTIVE changes. Apply is blocked until re-reviewed.');
            } else {
                statusEl.textContent = '✓ Ready';
                statusEl.className = 'badge badge-approved';
                const summary = data.summary ? ` (${data.summary})` : '';
                this.addChatMessage('system', `✓ Plan generated successfully${summary}. Review output and click Apply when ready.`);
            }

            this.updateApplyButton();
            this.loadPRStatus();
            this.setWorkflowStep(5);
            if (typeof refreshLogsIfVisible === 'function') refreshLogsIfVisible();
        }
    },

    updateApplyButton() {
        const btn = document.getElementById('applyBtn');
        const hint = document.getElementById('applyHint');

        if (!this.diffConfirmed || !this.planReviewed) {
            btn.disabled = true;
            btn.classList.remove('destructive-blocked');
            hint.textContent = 'Apply is disabled until plan is reviewed';
            return;
        }

        if (this.planDestructive) {
            btn.disabled = true;
            btn.classList.add('destructive-blocked');
            hint.textContent = '⚠ Apply blocked — plan contains destructive changes';
            return;
        }

        if (!this.prApproved) {
            btn.disabled = true;
            btn.classList.remove('destructive-blocked');
            hint.textContent = 'Approve the pull request before applying';
            return;
        }

        btn.disabled = false;
        btn.classList.remove('destructive-blocked');
        hint.textContent = 'Plan reviewed — ready to apply';
    },

    applyChanges() {
        if (!this.planReviewed || this.planDestructive || !this.prApproved) return;

        const applyOutput = document.getElementById('applyOutput');
        applyOutput.textContent = '';
        document.getElementById('applyStatus').textContent = 'Applying...';
        document.getElementById('applyStatus').className = 'badge badge-warn';
        document.getElementById('applyBtn').disabled = true;

        this.addChatMessage('system', '⚡ Applying infrastructure changes…');

        WSClient.applyPlan(this.getService(), this.getAccount(), this.currentMessage)
            .catch(err => {
                showToast(err.message, 'error');
                document.getElementById('applyBtn').disabled = false;
            });
    },

    handleApplyOutput(data) {
        const applyOutput = document.getElementById('applyOutput');

        if (data.type === 'apply_line') {
            const line = document.createElement('div');
            line.textContent = data.line;
            if (/complete|passed|OK/i.test(data.line)) line.className = 'line-add';
            if (/error|fail/i.test(data.line)) line.className = 'line-destroy';
            applyOutput.appendChild(line);
            applyOutput.scrollTop = applyOutput.scrollHeight;
        }

        if (data.type === 'apply_complete') {
            const statusEl = document.getElementById('applyStatus');
            if (data.success) {
                statusEl.textContent = '✓ Complete';
                statusEl.className = 'badge badge-approved';
                showToast('Apply completed successfully!', 'success');
                this.addChatMessage('system', '✓ Apply complete! Resources updated successfully.');
                if (typeof refreshLogsIfVisible === 'function') refreshLogsIfVisible();
            } else {
                statusEl.textContent = '✗ Failed';
                statusEl.className = 'badge badge-danger';
                showToast('Apply failed', 'error');
            }
            this.updateApplyButton();
        }
    },

    async loadPRStatus() {
        try {
            const service = this.getService();
            const account = this.getAccount();
            const res = await Auth.apiFetch(`/pr/status?service=${service}&account=${account}`);
            const data = await res.json();
            const pr = data.pullRequest;
            const required = pr.approvals_required || 1;
            const received = pr.approvals_received || 0;

            document.getElementById('prLink').textContent = `#${pr.pr_number} — ${(pr.title || '').replace('[SSP]', '[SmartOps Portal]').replace('[My Portal]', '[SmartOps Portal]')}`;
            document.getElementById('prLink').href = pr.url;

            const statusEl = document.getElementById('prStatus');
            statusEl.textContent = pr.status;
            statusEl.className = `badge badge-${pr.status === 'approved' ? 'approved' : 'open'}`;

            document.getElementById('prApprovalCount').textContent =
                `${Math.min(received, required)} / ${required}`;

            const pct = required > 0 ? (Math.min(received, required) / required) * 100 : 0;
            document.getElementById('prApprovalBar').style.width = `${pct}%`;

            this.prApproved = pr.status === 'approved' || received >= required;

            const approveBtn = document.getElementById('approvePrBtn');
            if (this.prApproved) {
                approveBtn.disabled = true;
                approveBtn.textContent = '✓ PR Approved';
                approveBtn.classList.add('approved');
            } else {
                approveBtn.disabled = false;
                approveBtn.textContent = 'Approve PR';
                approveBtn.classList.remove('approved');
            }

            this.updateApplyButton();
        } catch (err) {
            console.warn('PR status load failed:', err);
        }
    },

    async approvePR() {
        try {
            const service = this.getService();
            const account = this.getAccount();
            const res = await Auth.apiFetch(`/pr/status?service=${service}&account=${account}`);
            const data = await res.json();
            const prNumber = data.pullRequest.pr_number;

            const approveRes = await Auth.apiFetch('/pr/approve', {
                method: 'POST',
                body: JSON.stringify({ prNumber }),
            });
            const result = await approveRes.json();
            if (!approveRes.ok) throw new Error(result.error || 'Approval failed');

            const required = result.approvalsRequired || 1;
            const received = result.approvalsReceived || 1;
            showToast(`PR approved (${received}/${required})`, 'success');
            this.addChatMessage('system', `✓ Pull request approved (${received}/${required}). Click Apply to deploy.`);
            await this.loadPRStatus();
            this.updateApplyButton();

            document.getElementById('applySection')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            document.getElementById('applyOutputSection')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        } catch (err) {
            showToast('Failed to approve PR: ' + err.message, 'error');
        }
    },

    resetWorkflow() {
        this.planReviewed = false;
        this.planDestructive = false;
        this.diffConfirmed = false;
        document.getElementById('yamlDiffSection').hidden = true;
        document.getElementById('diffSummary').hidden = true;
        document.getElementById('yamlDiffSection').querySelector('.diff-actions').hidden = false;
        document.getElementById('planOutput').innerHTML = '';
        document.getElementById('applyOutput').innerHTML = '';
        document.getElementById('planStatus').textContent = 'No plan';
        document.getElementById('planStatus').className = 'badge badge-muted';
        document.getElementById('applyStatus').textContent = 'Idle';
        document.getElementById('applyStatus').className = 'badge badge-muted';
        this.updateApplyButton();
        this.setWorkflowStep(1);
    },
};
