const API_BASE = `${window.location.origin}/api`;
const TOKEN_KEY = 'ssp_token';
const USER_KEY = 'ssp_user';

const Auth = {
    getToken() {
        return localStorage.getItem(TOKEN_KEY);
    },

    getUser() {
        const raw = localStorage.getItem(USER_KEY);
        return raw ? JSON.parse(raw) : null;
    },

    setSession(token, user) {
        localStorage.setItem(TOKEN_KEY, token);
        localStorage.setItem(USER_KEY, JSON.stringify(user));
    },

    clearSession() {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(USER_KEY);
    },

    isAuthenticated() {
        return !!this.getToken();
    },

    authHeaders() {
        return {
            'Authorization': `Bearer ${this.getToken()}`,
            'Content-Type': 'application/json',
        };
    },

    async login(username, password) {
        const res = await fetch(`${API_BASE}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Login failed');
        this.setSession(data.token, data.user);
        return data.user;
    },

    async signup(username, email, password, confirmPassword) {
        const res = await fetch(`${API_BASE}/auth/signup`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, email, password, confirmPassword }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Signup failed');
        return data;
    },

    async verify() {
        const token = this.getToken();
        if (!token) return null;
        try {
            const res = await fetch(`${API_BASE}/auth/me`, {
                headers: { 'Authorization': `Bearer ${token}` },
            });
            if (!res.ok) {
                this.clearSession();
                return null;
            }
            const data = await res.json();
            this.setSession(token, data.user);
            return data.user;
        } catch {
            return null;
        }
    },

    async logout() {
        try {
            await fetch(`${API_BASE}/auth/logout`, {
                method: 'POST',
                headers: this.authHeaders(),
            });
        } catch { /* ignore */ }
        this.clearSession();
    },

    async apiFetch(path, options = {}) {
        const headers = { ...this.authHeaders(), ...(options.headers || {}) };
        const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
        if (res.status === 401) {
            this.clearSession();
            window.location.reload();
            throw new Error('Session expired');
        }
        return res;
    },
};
