"""SQLite persistence for SSP users, sessions, and audit logs."""
import sqlite3
import os
import re
import secrets
import string
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), 'ssp_data.db')
USER_STATUSES = ('pending', 'approved', 'rejected', 'disabled')


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'operator',
            status TEXT DEFAULT 'approved',
            created_at TEXT NOT NULL,
            updated_at TEXT,
            approved_by INTEGER,
            approved_at TEXT
        );
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            action TEXT NOT NULL,
            service TEXT,
            account TEXT,
            details TEXT,
            level TEXT DEFAULT 'info',
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            service TEXT,
            account TEXT,
            messages TEXT DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS pull_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pr_number INTEGER NOT NULL,
            title TEXT,
            url TEXT NOT NULL,
            status TEXT DEFAULT 'open',
            approvals_required INTEGER DEFAULT 1,
            approvals_received INTEGER DEFAULT 0,
            service TEXT,
            account TEXT,
            created_at TEXT NOT NULL
        );
    ''')
    conn.commit()
    _migrate_users_table(conn)
    _migrate_pull_requests(conn)
    _seed_admin_user(conn)
    conn.close()


def _migrate_pull_requests(conn):
    """Ensure all PRs require only one approval."""
    cur = conn.cursor()
    cur.execute('UPDATE pull_requests SET approvals_required = 1')
    cur.execute(
        "UPDATE pull_requests SET status = 'approved' "
        "WHERE approvals_received >= 1 AND status != 'approved'"
    )
    cur.execute('UPDATE pull_requests SET approvals_received = 1 WHERE approvals_received > 1')
    conn.commit()


def normalize_pr(pr):
    """Single-approval gate: required=1, cap received, auto-approve when met."""
    if not pr:
        return pr
    pr = dict(pr)
    required = 1
    received = min(int(pr.get('approvals_received') or 0), required)
    pr['approvals_required'] = required
    pr['approvals_received'] = received
    if received >= required:
        pr['status'] = 'approved'
    return pr


def _migrate_users_table(conn):
    cur = conn.cursor()
    cols = {row[1] for row in cur.execute('PRAGMA table_info(users)').fetchall()}
    migrations = {
        'status': "ALTER TABLE users ADD COLUMN status TEXT DEFAULT 'approved'",
        'updated_at': 'ALTER TABLE users ADD COLUMN updated_at TEXT',
        'approved_by': 'ALTER TABLE users ADD COLUMN approved_by INTEGER',
        'approved_at': 'ALTER TABLE users ADD COLUMN approved_at TEXT',
    }
    for col, sql in migrations.items():
        if col not in cols:
            cur.execute(sql)
    cur.execute("UPDATE users SET status = 'approved' WHERE status IS NULL OR status = ''")
    conn.commit()


def _generate_temp_password(length=16):
    alphabet = string.ascii_letters + string.digits + '!@#$%'
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def _seed_admin_user(conn):
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) FROM users')
    if cur.fetchone()[0] > 0:
        return

    now = datetime.utcnow().isoformat()
    admin_password = os.environ.get('ADMIN_PASSWORD')
    generated = False
    if not admin_password:
        admin_password = _generate_temp_password()
        generated = True

    cur.execute(
        '''INSERT INTO users
           (username, email, password_hash, role, status, created_at, updated_at, approved_at)
           VALUES (?,?,?,?,?,?,?,?)''',
        (
            'admin',
            os.environ.get('ADMIN_EMAIL', 'admin@portal.local'),
            generate_password_hash(admin_password),
            'admin',
            'approved',
            now,
            now,
            now,
        ),
    )
    conn.commit()
    if generated:
        print('=' * 60)
        print('Initial admin account created.')
        print('Username: admin')
        print(f'Password: {admin_password}')
        print('Set ADMIN_PASSWORD env var to use a fixed password on fresh installs.')
        print('=' * 60)


def _public_user(row):
    if not row:
        return None
    data = dict(row)
    return {
        'id': data['id'],
        'username': data['username'],
        'email': data['email'],
        'role': data['role'],
        'status': data.get('status', 'approved'),
        'created_at': data['created_at'],
        'updated_at': data.get('updated_at'),
        'approved_at': data.get('approved_at'),
    }


def _validate_username(username):
    if not re.fullmatch(r'[A-Za-z0-9_]{3,32}', username or ''):
        return 'Username must be 3-32 characters (letters, numbers, underscore only)'
    return None


def _validate_email(email):
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email or ''):
        return 'Valid email address is required'
    return None


def _validate_password(password):
    if len(password or '') < 8:
        return 'Password must be at least 8 characters'
    return None


def authenticate_user(username, password):
    conn = get_conn()
    row = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()
    if not row or not check_password_hash(row['password_hash'], password):
        return None
    user = dict(row)
    status = user.get('status') or 'approved'
    if status != 'approved':
        user['_auth_blocked'] = status
    return user


def create_signup_request(username, email, password):
    username_err = _validate_username(username)
    if username_err:
        return None, username_err
    email_err = _validate_email(email)
    if email_err:
        return None, email_err
    password_err = _validate_password(password)
    if password_err:
        return None, password_err

    conn = get_conn()
    existing = conn.execute(
        'SELECT username, email, status FROM users WHERE username = ? OR email = ?',
        (username, email),
    ).fetchone()
    if existing:
        conn.close()
        if existing['username'] == username:
            return None, 'Username is already taken'
        return None, 'Email is already registered'

    now = datetime.utcnow().isoformat()
    conn.execute(
        '''INSERT INTO users
           (username, email, password_hash, role, status, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?)''',
        (username, email, generate_password_hash(password), 'operator', 'pending', now, now),
    )
    conn.commit()
    row = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()
    return _public_user(dict(row)), None


def get_pending_users():
    conn = get_conn()
    rows = conn.execute(
        '''SELECT id, username, email, role, status, created_at, updated_at
           FROM users WHERE status = 'pending' ORDER BY created_at ASC'''
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def approve_user(user_id, admin_id):
    conn = get_conn()
    row = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    if not row:
        conn.close()
        return None, 'User not found'
    if row['status'] != 'pending':
        conn.close()
        return None, 'User is not pending approval'

    now = datetime.utcnow().isoformat()
    conn.execute(
        '''UPDATE users
           SET status = 'approved', approved_by = ?, approved_at = ?, updated_at = ?
           WHERE id = ?''',
        (admin_id, now, now, user_id),
    )
    conn.commit()
    updated = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    return _public_user(dict(updated)), None


def reject_user(user_id, admin_id):
    conn = get_conn()
    row = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    if not row:
        conn.close()
        return None, 'User not found'
    if row['status'] != 'pending':
        conn.close()
        return None, 'User is not pending approval'

    now = datetime.utcnow().isoformat()
    conn.execute(
        '''UPDATE users
           SET status = 'rejected', approved_by = ?, updated_at = ?
           WHERE id = ?''',
        (admin_id, now, user_id),
    )
    conn.commit()
    updated = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    return _public_user(dict(updated)), None


def get_user_by_id(user_id):
    conn = get_conn()
    row = conn.execute(
        'SELECT id, username, email, role, status, created_at, updated_at, approved_at FROM users WHERE id = ?',
        (user_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_username(username):
    conn = get_conn()
    row = conn.execute(
        'SELECT id, username, email, role, status, created_at, updated_at, approved_at FROM users WHERE username = ?',
        (username,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def add_audit_log(user_id, username, action, service=None, account=None, details=None, level='info'):
    conn = get_conn()
    conn.execute(
        'INSERT INTO audit_logs (user_id, username, action, service, account, details, level, created_at) VALUES (?,?,?,?,?,?,?,?)',
        (user_id, username, action, service, account, details, level, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()


def get_audit_logs(limit=100, user_id=None):
    conn = get_conn()
    if user_id:
        rows = conn.execute(
            'SELECT * FROM audit_logs WHERE user_id = ? ORDER BY id DESC LIMIT ?',
            (user_id, limit)
        ).fetchall()
    else:
        rows = conn.execute('SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def upsert_pr(pr_number, title, url, status, approvals_required, approvals_received, service, account):
    conn = get_conn()
    existing = conn.execute('SELECT id FROM pull_requests WHERE pr_number = ?', (pr_number,)).fetchone()
    now = datetime.utcnow().isoformat()
    if existing:
        conn.execute(
            '''UPDATE pull_requests SET title=?, url=?, status=?, approvals_required=?,
               approvals_received=?, service=?, account=? WHERE pr_number=?''',
            (title, url, status, approvals_required, approvals_received, service, account, pr_number)
        )
    else:
        conn.execute(
            '''INSERT INTO pull_requests (pr_number, title, url, status, approvals_required,
               approvals_received, service, account, created_at) VALUES (?,?,?,?,?,?,?,?,?)''',
            (pr_number, title, url, status, approvals_required, approvals_received, service, account, now)
        )
    conn.commit()
    conn.close()


def get_latest_pr(service=None, account=None):
    conn = get_conn()
    if service and account:
        row = conn.execute(
            'SELECT * FROM pull_requests WHERE service=? AND account=? ORDER BY id DESC LIMIT 1',
            (service, account)
        ).fetchone()
    else:
        row = conn.execute('SELECT * FROM pull_requests ORDER BY id DESC LIMIT 1').fetchone()
    conn.close()
    return normalize_pr(dict(row) if row else None)
