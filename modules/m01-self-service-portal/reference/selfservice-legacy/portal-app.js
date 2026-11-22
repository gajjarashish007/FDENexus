const VIEW_TITLES = {
    sspView: 'Provisioner',
    dashboardView: 'Resource Dashboard',
    servicesView: 'Service Catalog',
    logsView: 'Audit Log History',
    helpView: 'User Guide',
    deploymentsView: 'Manage Deployments',
    adminView: 'User Approvals',
};

const THEME_KEY = 'portal_theme';
let allLogsCache = [];

const ACTION_LABELS = {
    chat_message: 'Infrastructure Chat',
    yaml_diff_generated: 'YAML Diff Generated',
    yaml_diff_confirmed: 'YAML Diff Confirmed',
    yaml_diff_rejected: 'YAML Diff Rejected',
    plan_started: 'Terraform Plan Started',
    plan_complete: 'Terraform Plan Complete',
    apply_started: 'Apply Started',
    apply_complete: 'Apply Complete',
    pr_approved: 'PR Approved',
    login: 'Login',
    logout: 'Logout',
    signup_request: 'Signup Request',
    user_approved: 'User Approved',
    user_rejected: 'User Rejected',
    deploy_create: 'Deployment Created',
    deploy_rerun: 'Deployment Rerun',
    deploy_edit: 'Deployment Updated',
    deploy_destroy: 'Deployment Destroyed',
};

const INFRA_ACTIONS = new Set([
    'chat_message', 'yaml_diff_generated', 'yaml_diff_confirmed', 'yaml_diff_rejected',
    'plan_started', 'plan_complete', 'apply_started', 'apply_complete', 'pr_approved',
]);

function formatLogAction(action) {
    return ACTION_LABELS[action] || (action || '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function refreshLogsIfVisible() {
    const logsView = document.getElementById('logsView');
    if (logsView?.classList.contains('active')) {
        loadLogs();
    }
}

function showToast(message, type = 'info') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = `toast ${type} show`;
    setTimeout(() => toast.classList.remove('show'), 3500);
}

function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(THEME_KEY, theme);
    const select = document.getElementById('themeSelect');
    if (select) select.value = theme;
}

function initTheme() {
    const saved = localStorage.getItem(THEME_KEY) || 'dark';
    applyTheme(saved);
}

function setPageView(mode) {
    const login = document.getElementById('loginView');
    const portal = document.getElementById('portalShell');

    if (mode === 'portal') {
        login.hidden = true;
        login.classList.remove('page-active');
        portal.hidden = false;
        portal.classList.add('page-active');
        document.body.classList.remove('login-mode');
        document.body.classList.add('portal-mode');
    } else {
        login.hidden = false;
        login.classList.add('page-active');
        portal.hidden = true;
        portal.classList.remove('page-active');
        document.body.classList.add('login-mode');
        document.body.classList.remove('portal-mode');
    }
}

async function checkApiHealth() {
    const el = document.getElementById('apiStatus');
    if (!el) return;
    try {
        const res = await fetch(`${window.location.origin}/api/health`);
        const data = await res.json();
        if (res.ok && data.status === 'healthy') {
            el.textContent = data.aws === 'connected' ? 'API + AWS Connected' : 'API Online (AWS offline)';
            el.className = 'api-badge connected';
        } else {
            throw new Error('Unhealthy');
        }
    } catch {
        el.textContent = 'API Offline';
        el.className = 'api-badge';
    }
}

function switchView(viewId) {
    document.querySelectorAll('.view-panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav-module').forEach(n => n.classList.remove('active'));

    const panel = document.getElementById(viewId);
    const navBtn = document.querySelector(`[data-view="${viewId}"]`);

    if (panel) panel.classList.add('active');
    if (navBtn) navBtn.classList.add('active');

    document.getElementById('viewTitle').textContent = VIEW_TITLES[viewId] || viewId;

    if (viewId === 'logsView') loadLogs();
    if (viewId === 'deploymentsView') ManageDeployments.load();
    if (viewId === 'adminView') AdminUsers.load();
}

function showAuthForm(mode) {
    const loginForm = document.getElementById('loginForm');
    const signupForm = document.getElementById('signupForm');
    const loginError = document.getElementById('loginError');
    const signupError = document.getElementById('signupError');
    const signupSuccess = document.getElementById('signupSuccess');

    loginError.hidden = true;
    signupError.hidden = true;
    signupSuccess.hidden = true;

    if (mode === 'signup') {
        loginForm.hidden = true;
        signupForm.hidden = false;
    } else {
        loginForm.hidden = false;
        signupForm.hidden = true;
    }
}

function configureAdminNav(user) {
    const isAdmin = user?.role === 'admin';
    document.querySelectorAll('.admin-only').forEach(el => {
        el.hidden = !isAdmin;
    });
    document.querySelectorAll('.admin-only-nav').forEach(el => {
        el.hidden = !isAdmin;
    });
    if (isAdmin) {
        AdminUsers.load();
    }
}

async function loadLogs() {
    const tbody = document.getElementById('logsTableBody');
    tbody.innerHTML = '<tr><td colspan="7" class="logs-empty">Loading logs...</td></tr>';

    try {
        const res = await Auth.apiFetch('/logs?limit=100');
        const data = await res.json();
        allLogsCache = data.logs;
        renderLogs(allLogsCache);
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="7" class="logs-empty">Failed to load logs: ${err.message}</td></tr>`;
    }
}

function renderLogs(logs) {
    const tbody = document.getElementById('logsTableBody');
    const search = (document.getElementById('logsSearch')?.value || '').toLowerCase();
    const level = document.getElementById('logsLevelFilter')?.value || '';
    const actionFilter = document.getElementById('logsActionFilter')?.value || '';

    let filtered = logs;
    if (search) {
        filtered = filtered.filter(log =>
            (log.username || '').toLowerCase().includes(search) ||
            (log.action || '').toLowerCase().includes(search) ||
            formatLogAction(log.action).toLowerCase().includes(search) ||
            (log.service || '').toLowerCase().includes(search) ||
            (log.details || '').toLowerCase().includes(search)
        );
    }
    if (level) {
        filtered = filtered.filter(log => log.level === level);
    }
    if (actionFilter === 'infra') {
        filtered = filtered.filter(log => INFRA_ACTIONS.has(log.action));
    } else if (actionFilter === 'auth') {
        filtered = filtered.filter(log => ['login', 'logout', 'signup_request', 'user_approved', 'user_rejected', 'login_blocked'].includes(log.action));
    } else if (actionFilter === 'deploy') {
        filtered = filtered.filter(log => (log.action || '').startsWith('deploy_'));
    }

    document.getElementById('logsCount').textContent = `${filtered.length} entries`;

    if (filtered.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="logs-empty">No matching log entries</td></tr>';
        return;
    }

    tbody.innerHTML = filtered.map(log => {
        const time = new Date(log.created_at).toLocaleString();
        const actionLabel = formatLogAction(log.action);
        const details = log.details || '—';
        return `<tr>
            <td>${time}</td>
            <td>${log.username || '—'}</td>
            <td><span class="log-action" title="${log.action}">${actionLabel}</span></td>
            <td>${log.service || '—'}</td>
            <td>${log.account || '—'}</td>
            <td class="log-details">${details}</td>
            <td><span class="log-level ${log.level}">${log.level}</span></td>
        </tr>`;
    }).join('');
}

function exportLogsCSV() {
    if (!allLogsCache.length) {
        showToast('No logs to export', 'info');
        return;
    }
    const headers = ['Time', 'User', 'Action', 'Service', 'Account', 'Details', 'Level'];
    const rows = allLogsCache.map(log => [
        log.created_at, log.username, formatLogAction(log.action), log.service || '',
        log.account || '', (log.details || '').replace(/"/g, '""'), log.level
    ]);
    const csv = [headers, ...rows].map(r => r.map(c => `"${c || ''}"`).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `smartops-portal-logs-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    showToast('Logs exported!', 'success');
}

let portalInitialized = false;

function showPortal(user) {
    setPageView('portal');

    document.getElementById('userName').textContent = user.username;
    document.getElementById('userRole').textContent = user.role;
    document.getElementById('userAvatar').textContent = user.username[0].toUpperCase();
    configureAdminNav(user);

    if (!portalInitialized) {
        WSClient.connect();
        SSP.init();
        checkApiHealth();
        setInterval(checkApiHealth, 30000);
        if (!document.getElementById('chatWelcome')) {
            SSP.addChatMessage('system',
                'Welcome to SmartOps Portal. Select a service and account, then describe the infrastructure change you need.'
            );
        }
        portalInitialized = true;
    }

    switchView('sspView');
}

function showLogin() {
    setPageView('login');
    showAuthForm('login');
    WSClient.disconnect();
    portalInitialized = false;
}

document.addEventListener('DOMContentLoaded', async () => {
    initTheme();

    document.getElementById('themeSelect').addEventListener('change', (e) => {
        applyTheme(e.target.value);
        showToast(`Theme: ${e.target.options[e.target.selectedIndex].text}`, 'info');
    });

    document.getElementById('loginForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const errorEl = document.getElementById('loginError');
        errorEl.hidden = true;

        const username = document.getElementById('loginUser').value.trim();
        const password = document.getElementById('loginPass').value;

        try {
            const user = await Auth.login(username, password);
            showPortal(user);
            showToast(`Welcome, ${user.username}!`, 'success');
        } catch (err) {
            errorEl.textContent = err.message;
            errorEl.hidden = false;
        }
    });

    document.getElementById('signupForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const errorEl = document.getElementById('signupError');
        const successEl = document.getElementById('signupSuccess');
        errorEl.hidden = true;
        successEl.hidden = true;

        const username = document.getElementById('signupUser').value.trim();
        const email = document.getElementById('signupEmail').value.trim();
        const password = document.getElementById('signupPass').value;
        const confirmPassword = document.getElementById('signupConfirm').value;

        if (password !== confirmPassword) {
            errorEl.textContent = 'Passwords do not match';
            errorEl.hidden = false;
            return;
        }

        try {
            const data = await Auth.signup(username, email, password, confirmPassword);
            successEl.textContent = data.message;
            successEl.hidden = false;
            document.getElementById('signupForm').reset();
            setTimeout(() => showAuthForm('login'), 4000);
        } catch (err) {
            errorEl.textContent = err.message;
            errorEl.hidden = false;
        }
    });

    document.getElementById('showSignupBtn')?.addEventListener('click', () => showAuthForm('signup'));
    document.getElementById('showLoginBtn')?.addEventListener('click', () => showAuthForm('login'));

    document.getElementById('logoutBtn').addEventListener('click', async () => {
        await Auth.logout();
        showLogin();
        showToast('Logged out', 'info');
    });

    document.querySelectorAll('.nav-module').forEach(btn => {
        btn.addEventListener('click', () => switchView(btn.dataset.view));
    });

    document.getElementById('refreshLogsBtn').addEventListener('click', loadLogs);
    document.getElementById('exportLogsBtn').addEventListener('click', exportLogsCSV);
    document.getElementById('logsSearch').addEventListener('input', () => renderLogs(allLogsCache));
    document.getElementById('logsLevelFilter').addEventListener('change', () => renderLogs(allLogsCache));
    document.getElementById('logsActionFilter')?.addEventListener('change', () => renderLogs(allLogsCache));
    document.getElementById('helpBtn').addEventListener('click', () => switchView('helpView'));

    ManageDeployments.init();
    AdminUsers.init();
    UserGuide.init();

    const user = await Auth.verify();
    if (user) {
        showPortal(user);
    } else {
        showLogin();
    }
});
