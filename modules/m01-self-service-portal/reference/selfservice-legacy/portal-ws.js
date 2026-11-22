const WS_URL = window.location.origin;

const WSClient = {
    socket: null,
    connected: false,
    usePolling: true,
    listeners: { plan: [], apply: [], error: [] },

    connect() {
        const token = Auth.getToken();
        if (!token) return;

        if (this.socket) {
            this.socket.disconnect();
        }

        this.socket = io(WS_URL, {
            query: { token },
            transports: ['polling'],
            upgrade: false,
            reconnection: true,
            reconnectionAttempts: 15,
            reconnectionDelay: 2000,
            timeout: 20000,
        });

        this.socket.on('connect', () => {
            this.connected = true;
            this._updateBadge(true, 'polling');
        });

        this.socket.on('disconnect', () => {
            this.connected = false;
            this._updateBadge(false);
        });

        this.socket.on('connect_error', (err) => {
            console.warn('[WS] connect_error — will use REST fallback:', err.message);
            this.connected = false;
            this._updateBadge(false);
        });

        this.socket.on('connected', (data) => {
            console.log('[WS] Connected:', data.message);
        });

        this.socket.on('plan_output', (data) => {
            this.listeners.plan.forEach(fn => fn(data));
        });

        this.socket.on('apply_output', (data) => {
            this.listeners.apply.forEach(fn => fn(data));
        });

        this.socket.on('error', (data) => {
            this.listeners.error.forEach(fn => fn(data));
        });
    },

    disconnect() {
        if (this.socket) {
            this.socket.disconnect();
            this.socket = null;
        }
        this.connected = false;
        this._updateBadge(false);
    },

    on(event, callback) {
        if (this.listeners[event]) {
            this.listeners[event].push(callback);
        }
    },

    generatePlan(service, account, message) {
        if (this.connected && this.socket) {
            this.socket.emit('generate_plan', { service, account, message });
            return Promise.resolve('socket');
        }
        return this._streamPlanREST(service, account, message);
    },

    applyPlan(service, account, message) {
        if (this.connected && this.socket) {
            this.socket.emit('apply_plan', { service, account, message });
            return Promise.resolve('socket');
        }
        return this._streamApplyREST(service, account, message);
    },

    async _streamPlanREST(service, account, message) {
        const res = await Auth.apiFetch('/plan/stream', {
            method: 'POST',
            body: JSON.stringify({ service, account, message }),
        });
        await this._readSSE(res, 'plan');
        return 'rest';
    },

    async _streamApplyREST(service, account, message) {
        const res = await Auth.apiFetch('/plan/apply-stream', {
            method: 'POST',
            body: JSON.stringify({ service, account, message }),
        });
        await this._readSSE(res, 'apply');
        return 'rest';
    },

    async _readSSE(response, channel) {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const parts = buffer.split('\n\n');
            buffer = parts.pop() || '';

            for (const part of parts) {
                const line = part.trim();
                if (!line.startsWith('data:')) continue;
                try {
                    const data = JSON.parse(line.slice(5).trim());
                    const event = channel === 'plan' ? 'plan' : 'apply';
                    this.listeners[event].forEach(fn => fn(data));
                } catch (e) {
                    console.warn('SSE parse error:', e);
                }
            }
        }
    },

    _updateBadge(connected, mode) {
        const el = document.getElementById('wsStatus');
        if (!el) return;
        if (connected) {
            el.textContent = mode === 'polling' ? 'Live (Polling)' : 'WS Connected';
            el.className = 'ws-badge connected';
        } else {
            el.textContent = 'REST Fallback';
            el.className = 'ws-badge disconnected';
        }
    },
};
