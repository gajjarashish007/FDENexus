"""SSP Portal backend extensions — auth, middleware, WebSocket, logs."""
import os
import json
import time
import threading
from functools import wraps
from datetime import datetime, timedelta

import jwt
from flask import request, jsonify, Response
from flask_socketio import emit, join_room, disconnect

import ssp_store
import ssp_middleware

JWT_SECRET = os.environ.get('JWT_SECRET', 'ssp-portal-secret-change-in-production')
JWT_EXPIRY_HOURS = 24


def create_token(user):
    payload = {
        'sub': str(user['id']),
        'username': user['username'],
        'role': user['role'],
        'exp': datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')


def decode_token(token):
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
    except jwt.PyJWTError:
        return None


def auth_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Authentication required'}), 401
        token = auth_header[7:]
        payload = decode_token(token)
        if not payload:
            return jsonify({'error': 'Invalid or expired token'}), 401
        request.current_user = ssp_store.get_user_by_id(int(payload['sub']))
        if not request.current_user:
            return jsonify({'error': 'User not found'}), 401
        if request.current_user.get('status') != 'approved':
            return jsonify({'error': 'Account is not active'}), 403
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    @auth_required
    def decorated(*args, **kwargs):
        if request.current_user.get('role') != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated


def register_ssp_routes(app, socketio):
    ssp_store.init_db()

    # ── Auth ──────────────────────────────────────────────
    @app.route('/api/auth/login', methods=['POST'])
    def login():
        data = request.json or {}
        username = data.get('username', '').strip()
        password = data.get('password', '')
        if not username or not password:
            return jsonify({'error': 'Username and password required'}), 400
        user = ssp_store.authenticate_user(username, password)
        if not user:
            ssp_store.add_audit_log(None, username, 'login_failed', details='Invalid credentials', level='warn')
            return jsonify({'error': 'Invalid username or password'}), 401

        blocked = user.get('_auth_blocked')
        if blocked == 'pending':
            ssp_store.add_audit_log(user['id'], username, 'login_blocked', details='Pending approval', level='warn')
            return jsonify({
                'error': 'Your account is pending admin approval. You will be able to sign in once approved.',
                'status': 'pending',
            }), 403
        if blocked == 'rejected':
            return jsonify({
                'error': 'Your signup request was rejected. Contact an administrator.',
                'status': 'rejected',
            }), 403
        if blocked == 'disabled':
            return jsonify({
                'error': 'Your account has been disabled. Contact an administrator.',
                'status': 'disabled',
            }), 403

        token = create_token(user)
        ssp_store.add_audit_log(user['id'], user['username'], 'login', details='Successful login')
        return jsonify({
            'token': token,
            'user': {
                'id': user['id'],
                'username': user['username'],
                'email': user['email'],
                'role': user['role'],
                'status': user.get('status', 'approved'),
            }
        }), 200

    @app.route('/api/auth/signup', methods=['POST'])
    def signup():
        data = request.json or {}
        username = (data.get('username') or '').strip()
        email = (data.get('email') or '').strip().lower()
        password = data.get('password') or ''
        confirm = data.get('confirmPassword') or data.get('confirm_password') or ''

        if password != confirm:
            return jsonify({'error': 'Passwords do not match'}), 400

        user, err = ssp_store.create_signup_request(username, email, password)
        if err:
            return jsonify({'error': err}), 400

        ssp_store.add_audit_log(
            user['id'], username, 'signup_request',
            details=f'Signup requested for {email}', level='info'
        )
        return jsonify({
            'message': 'Signup submitted. An administrator must approve your account before you can sign in.',
            'user': user,
        }), 201

    @app.route('/api/auth/pending-users', methods=['GET'])
    @admin_required
    def pending_users():
        users = ssp_store.get_pending_users()
        return jsonify({'users': users}), 200

    @app.route('/api/auth/users/<int:user_id>/approve', methods=['POST'])
    @admin_required
    def approve_user(user_id):
        admin = request.current_user
        user, err = ssp_store.approve_user(user_id, admin['id'])
        if err:
            return jsonify({'error': err}), 400
        ssp_store.add_audit_log(
            admin['id'], admin['username'], 'user_approved',
            details=f'Approved user {user["username"]}', level='info'
        )
        return jsonify({'message': f'User "{user["username"]}" approved', 'user': user}), 200

    @app.route('/api/auth/users/<int:user_id>/reject', methods=['POST'])
    @admin_required
    def reject_user(user_id):
        admin = request.current_user
        user, err = ssp_store.reject_user(user_id, admin['id'])
        if err:
            return jsonify({'error': err}), 400
        ssp_store.add_audit_log(
            admin['id'], admin['username'], 'user_rejected',
            details=f'Rejected user {user["username"]}', level='warn'
        )
        return jsonify({'message': f'User "{user["username"]}" rejected', 'user': user}), 200

    @app.route('/api/auth/me', methods=['GET'])
    @auth_required
    def auth_me():
        return jsonify({'user': request.current_user}), 200

    @app.route('/api/auth/logout', methods=['POST'])
    @auth_required
    def logout():
        u = request.current_user
        ssp_store.add_audit_log(u['id'], u['username'], 'logout')
        return jsonify({'message': 'Logged out'}), 200

    # ── Middleware: services & accounts ───────────────────
    @app.route('/api/middleware/services', methods=['GET'])
    @auth_required
    def middleware_services():
        return jsonify({'services': ssp_middleware.get_services()}), 200

    @app.route('/api/middleware/accounts', methods=['GET'])
    @auth_required
    def middleware_accounts():
        return jsonify({'accounts': ssp_middleware.get_accounts()}), 200

    # ── Audit logs ────────────────────────────────────────
    CLIENT_LOG_ACTIONS = frozenset({
        'yaml_diff_confirmed', 'yaml_diff_rejected',
    })

    def _clip_details(text, limit=200):
        if not text:
            return None
        text = str(text).strip()
        return text[:limit] if len(text) > limit else text

    def _run_plan_with_audit(user, service, account, message, emit_fn):
        destructive = ssp_middleware.stream_plan(service, account, message, emit_fn)
        level = 'warn' if destructive else 'info'
        summary = 'Plan complete (destructive)' if destructive else 'Plan complete'
        ssp_store.add_audit_log(
            user['id'], user['username'], 'plan_complete',
            service=service, account=account,
            details=_clip_details(message) or summary, level=level,
        )

    def _run_apply_with_audit(user, service, account, message, emit_fn):
        ssp_middleware.stream_apply(service, account, emit_fn)
        ssp_store.add_audit_log(
            user['id'], user['username'], 'apply_complete',
            service=service, account=account,
            details=_clip_details(message) or 'Apply completed successfully', level='info',
        )

    @app.route('/api/logs', methods=['GET'])
    @auth_required
    def get_logs():
        limit = request.args.get('limit', 100, type=int)
        u = request.current_user
        logs = ssp_store.get_audit_logs(limit=limit) if u['role'] == 'admin' else ssp_store.get_audit_logs(limit=limit, user_id=u['id'])
        return jsonify({'logs': logs}), 200

    @app.route('/api/logs/record', methods=['POST'])
    @auth_required
    def record_client_log():
        data = request.json or {}
        action = data.get('action', '')
        if action not in CLIENT_LOG_ACTIONS:
            return jsonify({'error': 'Invalid action'}), 400
        u = request.current_user
        ssp_store.add_audit_log(
            u['id'], u['username'], action,
            service=data.get('service'), account=data.get('account'),
            details=_clip_details(data.get('details') or data.get('message')),
            level=data.get('level', 'info'),
        )
        return jsonify({'message': 'Log recorded'}), 200

    # ── Chat (streaming via SSE-like chunks in POST) ──────
    @app.route('/api/chat/stream', methods=['POST'])
    @auth_required
    def chat_stream():
        data = request.json or {}
        message = data.get('message', '')
        service = data.get('service', 'ec2')
        account = data.get('account', 'dev')
        history = data.get('history', [])

        reply = ssp_middleware.chat_response(message, service, account, history)
        u = request.current_user
        ssp_store.add_audit_log(
            u['id'], u['username'], 'chat_message',
            service=service, account=account,
            details=_clip_details(f'Chat: {message}'),
        )

        def generate():
            for line in reply.split('\n'):
                yield line + '\n'
                time.sleep(0.06)
        from flask import Response
        return Response(generate(), mimetype='text/plain')

    # ── YAML diff ─────────────────────────────────────────
    @app.route('/api/plan/yaml-diff', methods=['POST'])
    @auth_required
    def yaml_diff():
        data = request.json or {}
        service = data.get('service', 'ec2')
        account_id = data.get('account', 'dev')
        message = data.get('message', '')
        account = next((a for a in ssp_middleware.ACCOUNTS if a['id'] == account_id), ssp_middleware.ACCOUNTS[0])
        diff = ssp_middleware.generate_yaml_diff(service, account, message)
        u = request.current_user
        ssp_store.add_audit_log(
            u['id'], u['username'], 'yaml_diff_generated',
            service=service, account=account_id,
            details=_clip_details(message) or 'YAML diff generated', level='info',
        )
        return jsonify(diff), 200

    # ── Pull request status ───────────────────────────────
    @app.route('/api/pr/status', methods=['GET'])
    @auth_required
    def pr_status():
        service = request.args.get('service')
        account = request.args.get('account')
        pr = ssp_store.get_latest_pr(service=service, account=account)
        if not pr:
            pr_number = random_pr_number()
            service_name = service or 'ec2'
            account_name = account or 'dev'
            pr = {
                'pr_number': pr_number,
                'title': f'[SmartOps Portal] Update {service_name} in {account_name}',
                'url': f'https://github.com/org/infra/pull/{pr_number}',
                'status': 'open',
                'approvals_required': 1,
                'approvals_received': 0,
                'service': service_name,
                'account': account_name,
            }
            ssp_store.upsert_pr(**pr)
        else:
            pr['title'] = (pr.get('title') or '').replace('[SSP]', '[SmartOps Portal]').replace('[My Portal]', '[SmartOps Portal]')
        return jsonify({'pullRequest': pr}), 200

    @app.route('/api/pr/approve', methods=['POST'])
    @auth_required
    def pr_approve():
        data = request.json or {}
        pr_number = data.get('prNumber')
        pr = ssp_store.get_latest_pr()
        if pr and pr['pr_number'] == pr_number:
            if pr.get('status') == 'approved' and pr.get('approvals_received', 0) >= 1:
                return jsonify({
                    'message': 'PR already approved',
                    'approvalsReceived': 1,
                    'approvalsRequired': 1,
                    'status': 'approved',
                }), 200
            new_count = 1
            status = 'approved'
            ssp_store.upsert_pr(
                pr['pr_number'], pr['title'], pr['url'], status,
                1, new_count, pr['service'], pr['account']
            )
            u = request.current_user
            ssp_store.add_audit_log(u['id'], u['username'], 'pr_approved', details=f'PR #{pr_number}')
            return jsonify({
                'message': 'Approval recorded',
                'approvalsReceived': new_count,
                'approvalsRequired': 1,
                'status': status,
            }), 200
        return jsonify({'error': 'PR not found'}), 404

    # ── REST streaming fallback (SSE) for plan/apply ─────
    @app.route('/api/plan/stream', methods=['POST'])
    @auth_required
    def plan_stream():
        data = request.json or {}
        service = data.get('service', 'ec2')
        account = data.get('account', 'dev')
        message = data.get('message', '')
        u = request.current_user
        ssp_store.add_audit_log(
            u['id'], u['username'], 'plan_started',
            service=service, account=account,
            details=_clip_details(message) or 'Terraform plan started',
        )

        def generate():
            account_obj = next((a for a in ssp_middleware.ACCOUNTS if a['id'] == account), ssp_middleware.ACCOUNTS[0])
            destructive = any(w in message.lower() for w in ['delete', 'destroy', 'remove', 'terminate'])
            lines = ssp_middleware.generate_plan_lines(service, account_obj, destructive)
            for line in lines:
                payload = json.dumps({'type': 'plan_line', 'line': line})
                yield f'data: {payload}\n\n'
                time.sleep(0.08)
            payload = json.dumps({'type': 'plan_complete', 'destructive': destructive, 'summary': 'Plan complete'})
            yield f'data: {payload}\n\n'
            level = 'warn' if destructive else 'info'
            summary = 'Plan complete (destructive)' if destructive else 'Plan complete'
            ssp_store.add_audit_log(
                u['id'], u['username'], 'plan_complete',
                service=service, account=account,
                details=_clip_details(message) or summary, level=level,
            )

        return Response(generate(), mimetype='text/event-stream', headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        })

    @app.route('/api/plan/apply-stream', methods=['POST'])
    @auth_required
    def apply_stream():
        data = request.json or {}
        service = data.get('service', 'ec2')
        account = data.get('account', 'dev')
        message = data.get('message', '')
        u = request.current_user
        ssp_store.add_audit_log(
            u['id'], u['username'], 'apply_started',
            service=service, account=account,
            details=_clip_details(message) or 'Infrastructure apply started', level='warn',
        )

        def generate():
            events = []
            def collect(event_data):
                events.append(event_data)

            ssp_middleware.stream_apply(service, account, collect, delay=0.12)
            for event_data in events:
                yield f'data: {json.dumps(event_data)}\n\n'
            ssp_store.add_audit_log(
                u['id'], u['username'], 'apply_complete',
                service=service, account=account,
                details=_clip_details(message) or 'Apply completed successfully', level='info',
            )

        return Response(generate(), mimetype='text/event-stream', headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive',
        })

    # ── WebSocket events ──────────────────────────────────
    @socketio.on('connect')
    def ws_connect():
        token = request.args.get('token')
        if not token:
            disconnect()
            return False
        payload = decode_token(token)
        if not payload:
            disconnect()
            return False
        join_room(f"user_{payload['sub']}")
        emit('connected', {'message': 'WebSocket connected', 'userId': payload['sub']})

    @socketio.on('generate_plan')
    def ws_generate_plan(data):
        token = request.args.get('token')
        payload = decode_token(token) if token else None
        if not payload:
            emit('error', {'message': 'Unauthorized'})
            return
        service = data.get('service', 'ec2')
        account = data.get('account', 'dev')
        message = data.get('message', '')
        user = ssp_store.get_user_by_id(int(payload['sub']))
        room = f"user_{payload['sub']}"

        def emit_fn(event_data):
            socketio.emit('plan_output', event_data, room=room)

        ssp_store.add_audit_log(
            user['id'], user['username'], 'plan_started',
            service=service, account=account,
            details=_clip_details(message) or 'Terraform plan started',
        )
        threading.Thread(
            target=_run_plan_with_audit,
            args=(user, service, account, message, emit_fn),
            daemon=True
        ).start()

    @socketio.on('apply_plan')
    def ws_apply_plan(data):
        token = request.args.get('token')
        payload = decode_token(token) if token else None
        if not payload:
            emit('error', {'message': 'Unauthorized'})
            return
        service = data.get('service', 'ec2')
        account = data.get('account', 'dev')
        message = data.get('message', '')
        user = ssp_store.get_user_by_id(int(payload['sub']))
        room = f"user_{payload['sub']}"

        def emit_fn(event_data):
            socketio.emit('apply_output', event_data, room=room)

        ssp_store.add_audit_log(
            user['id'], user['username'], 'apply_started',
            service=service, account=account,
            details=_clip_details(message) or 'Infrastructure apply started', level='warn',
        )
        threading.Thread(
            target=_run_apply_with_audit,
            args=(user, service, account, message, emit_fn),
            daemon=True
        ).start()


def random_pr_number():
    import random
    return random.randint(100, 999)
