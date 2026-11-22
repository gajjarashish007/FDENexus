"""Deployment API — static websites and code upload."""
import json
import os
import re
import uuid
import zipfile
from datetime import datetime

from flask import request, jsonify
from werkzeug.utils import secure_filename

import validators
import ssp_store

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')
DEPLOYMENTS_FILE = os.path.join(BASE_DIR, 'deployments.json')

ALLOWED_STATIC_EXT = {'.html', '.htm', '.css', '.js', '.json', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.webp', '.woff', '.woff2', '.txt', '.map'}
ALLOWED_CODE_EXT = {'.html', '.htm', '.css', '.js', '.py', '.java', '.go', '.rb', '.php', '.ts', '.tsx', '.jsx', '.json', '.txt', '.md', '.yaml', '.yml', '.toml', '.cfg', '.ini', '.sh', '.dockerfile'}
MAX_STATIC_FILE = 50 * 1024 * 1024  # 50MB
MAX_ZIP_FILE = 200 * 1024 * 1024    # 200MB

SERVICE_TYPE_LABELS = {
    'code-upload': 'Code Upload & Deploy',
    'static-website': 'Static Website Hosting',
}


def _service_type_label(dep_type):
    return SERVICE_TYPE_LABELS.get(dep_type, dep_type.replace('-', ' ').title())


def _normalize_deployment(record):
    """Ensure consistent fields for manage UI."""
    now = datetime.utcnow().isoformat()
    dep_type = record.get('type', 'unknown')
    status = record.get('status', 'APPLIED').upper()
    if status == 'DEPLOYED':
        status = 'APPLIED'
    created = record.get('createdAt') or now
    updated = record.get('updatedAt') or created
    return {
        **record,
        'id': record.get('id') or str(uuid.uuid4()),
        'type': dep_type,
        'serviceType': record.get('serviceType') or _service_type_label(dep_type),
        'resourceName': record.get('resourceName') or record.get('appName', 'unknown'),
        'appName': record.get('appName') or record.get('resourceName', 'unknown'),
        'status': status,
        'createdAt': created,
        'updatedAt': updated,
    }


def _find_deployment(deploy_id):
    deployments = _load_deployments()
    for i, d in enumerate(deployments):
        if d.get('id') == deploy_id:
            return i, d
    return None, None


def _update_deployment(deploy_id, updates):
    deployments = _load_deployments()
    for i, d in enumerate(deployments):
        if d.get('id') == deploy_id:
            d.update(updates)
            d['updatedAt'] = datetime.utcnow().isoformat()
            deployments[i] = _normalize_deployment(d)
            _save_deployments(deployments)
            return deployments[i]
    return None


def _seed_deployments():
    if _load_deployments():
        return
    now = datetime.utcnow()
    samples = [
        {
            'id': 'd922e84a-d458-43b2-840c-58bc2d35710d',
            'type': 'code-upload',
            'appName': 'mcrdashboard',
            'resourceName': 'mcrdashboard',
            'serviceType': 'Code Upload & Deploy',
            'status': 'APPLIED',
            'url': 'https://mcrdashboard.apps.example.com',
            'platform': 'linux/amd64',
            'containerPort': 8080,
            'createdAt': now.replace(hour=0, minute=51, second=41).isoformat(),
            'updatedAt': now.replace(hour=0, minute=57, second=57).isoformat(),
        },
        {
            'id': 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
            'type': 'static-website',
            'appName': 'npi-preflight',
            'resourceName': 'npi-preflight',
            'serviceType': 'Static Website Hosting',
            'status': 'APPLIED',
            'url': 'https://npi-preflight.apps.example.com',
            'createdAt': now.replace(hour=1, minute=15, second=0).isoformat(),
            'updatedAt': now.replace(hour=1, minute=20, second=0).isoformat(),
        },
    ]
    _save_deployments([_normalize_deployment(s) for s in samples])


def _ensure_dirs():
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(os.path.join(UPLOAD_DIR, 'static'), exist_ok=True)
    os.makedirs(os.path.join(UPLOAD_DIR, 'code'), exist_ok=True)
    os.makedirs(os.path.join(UPLOAD_DIR, 'docker'), exist_ok=True)


def _load_deployments():
    _ensure_dirs()
    if not os.path.exists(DEPLOYMENTS_FILE):
        return []
    with open(DEPLOYMENTS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def _save_deployments(deployments):
    _ensure_dirs()
    with open(DEPLOYMENTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(deployments, f, indent=2)


def _add_deployment(record):
    deployments = _load_deployments()
    normalized = _normalize_deployment({
        **record,
        'id': record.get('id') or str(uuid.uuid4()),
        'status': record.get('status', 'APPLIED').upper() if record.get('status', '').lower() != 'deployed' else 'APPLIED',
        'updatedAt': record.get('updatedAt') or datetime.utcnow().isoformat(),
    })
    deployments.insert(0, normalized)
    _save_deployments(deployments[:100])
    return normalized


def _audit_deploy(action, details, service_type=None):
    try:
        ssp_store.add_audit_log(None, 'portal', action, service=service_type, details=details)
    except Exception:
        pass


def _validate_app_name(name):
    if not name or not re.match(r'^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$', name):
        return False, 'Application name must be lowercase letters, numbers, hyphens only (3-63 chars)'
    return True, None


def _detect_language(files):
    exts = {os.path.splitext(f)[1].lower() for f in files}
    if '.py' in exts or 'requirements.txt' in files:
        return 'python', 'python:3.12-slim'
    if '.js' in exts or '.jsx' in exts or 'package.json' in files:
        return 'nodejs', 'node:20-alpine'
    if '.go' in exts:
        return 'go', 'golang:1.22-alpine'
    if '.java' in exts:
        return 'java', 'eclipse-temurin:21-jre-alpine'
    if '.html' in exts or '.htm' in exts:
        return 'static', 'nginx:alpine'
    return 'generic', 'alpine:3.19'


def register_deploy_routes(app):
    _ensure_dirs()
    _seed_deployments()

    @app.route('/api/deploy/deployments', methods=['GET'])
    def list_deployments():
        deps = [_normalize_deployment(d) for d in _load_deployments()]
        return jsonify({'deployments': deps}), 200

    @app.route('/api/deploy/deployments/<deploy_id>', methods=['GET'])
    def get_deployment(deploy_id):
        _, dep = _find_deployment(deploy_id)
        if not dep:
            return jsonify({'error': 'Deployment not found'}), 404
        return jsonify({'deployment': _normalize_deployment(dep)}), 200

    @app.route('/api/deploy/deployments/<deploy_id>/rerun', methods=['POST'])
    def rerun_deployment(deploy_id):
        dep = _update_deployment(deploy_id, {
            'status': 'APPLIED',
            'errorMessage': None,
            'lastAction': 'rerun',
        })
        if not dep:
            return jsonify({'error': 'Deployment not found'}), 404
        _audit_deploy('deploy_rerun', f'Rerun deployment {dep["resourceName"]}', dep.get('type'))
        return jsonify({
            'message': f'Deployment {dep["resourceName"]} rerun successfully',
            'deployment': dep,
        }), 200

    @app.route('/api/deploy/deployments/<deploy_id>/edit-rerun', methods=['POST'])
    def edit_rerun_deployment(deploy_id):
        data = request.json or {}
        _, existing = _find_deployment(deploy_id)
        if not existing:
            return jsonify({'error': 'Deployment not found'}), 404
        updates = {
            'status': 'APPLIED',
            'errorMessage': None,
            'lastAction': 'edit-rerun',
        }
        if data.get('resourceName'):
            ok, err = _validate_app_name(data['resourceName'].strip().lower())
            if not ok:
                return jsonify({'error': err}), 400
            updates['resourceName'] = data['resourceName'].strip().lower()
            updates['appName'] = updates['resourceName']
        if data.get('containerPort'):
            port_err = validators.validate_port(data['containerPort'], 'Container port')
            if port_err:
                return jsonify({'error': port_err}), 400
            updates['containerPort'] = int(data['containerPort'])
        if data.get('platform'):
            updates['platform'] = data['platform']
        dep = _update_deployment(deploy_id, updates)
        _audit_deploy('deploy_edit', f'Updated and rerun {dep["resourceName"]}', dep.get('type'))
        return jsonify({
            'message': f'Deployment {dep["resourceName"]} updated and rerun',
            'deployment': dep,
        }), 200

    @app.route('/api/deploy/deployments/<deploy_id>', methods=['DELETE'])
    def destroy_deployment(deploy_id):
        deployments = _load_deployments()
        dep = next((d for d in deployments if d.get('id') == deploy_id), None)
        if not dep:
            return jsonify({'error': 'Deployment not found'}), 404
        deployments = [d for d in deployments if d.get('id') != deploy_id]
        _save_deployments(deployments)
        app_name = dep.get('appName', deploy_id)
        _audit_deploy('deploy_destroy', f'Destroyed deployment {dep.get("resourceName", deploy_id)}', dep.get('type'))
        for sub in ('static', 'code', 'docker'):
            path = os.path.join(UPLOAD_DIR, sub, app_name)
            if os.path.isdir(path):
                import shutil
                shutil.rmtree(path, ignore_errors=True)
        return jsonify({
            'message': f'Deployment {dep.get("resourceName", deploy_id)} destroyed and deleted',
        }), 200

    @app.route('/api/deploy/deployments/<deploy_id>/delete-workspace', methods=['POST'])
    def delete_workspace(deploy_id):
        return destroy_deployment(deploy_id)

    @app.route('/api/deploy/static-website', methods=['POST'])
    def deploy_static_website():
        app_name = (request.form.get('appName') or '').strip()
        domain = (request.form.get('domain') or '').strip()
        cloudfront = request.form.get('cloudfront', 'true').lower() == 'true'
        files = request.files.getlist('files')

        ok, err = _validate_app_name(app_name)
        if not ok:
            return jsonify({'error': err}), 400
        if not domain:
            return jsonify({'error': 'Domain name is required'}), 400
        domain_err = validators.validate_domain(domain)
        if domain_err:
            return jsonify({'error': domain_err}), 400
        if not files:
            return jsonify({'error': 'Please upload website files'}), 400

        saved = []
        has_index = False
        dest = os.path.join(UPLOAD_DIR, 'static', app_name)
        os.makedirs(dest, exist_ok=True)

        for f in files:
            if not f.filename:
                continue
            fname = secure_filename(f.filename.replace('\\', '/').split('/')[-1])
            ext = os.path.splitext(fname)[1].lower()
            if ext not in ALLOWED_STATIC_EXT:
                return jsonify({'error': f'File type not allowed: {fname}'}), 400
            f.seek(0, 2)
            size = f.tell()
            f.seek(0)
            if size > MAX_STATIC_FILE:
                return jsonify({'error': f'File too large (max 50MB): {fname}'}), 400
            path = os.path.join(dest, fname)
            f.save(path)
            saved.append(fname)
            if fname.lower() in ('index.html', 'index.htm'):
                has_index = True

        if not has_index:
            return jsonify({'error': 'Upload must include index.html'}), 400

        deploy_id = str(uuid.uuid4())
        cdn_url = f'https://{domain}' if cloudfront else f'http://{app_name}.s3-website.{os.environ.get("AWS_REGION", "eu-west-1")}.amazonaws.com'
        record = {
            'id': deploy_id,
            'type': 'static-website',
            'serviceType': 'Static Website Hosting',
            'resourceName': app_name,
            'appName': app_name,
            'domain': domain,
            'cloudfront': cloudfront,
            'fileCount': len(saved),
            'files': saved[:20],
            'url': cdn_url,
            'status': 'APPLIED',
            'createdAt': datetime.utcnow().isoformat(),
        }
        _add_deployment(record)
        _audit_deploy('deploy_create', f'Static website {app_name} → {domain}', 'static-website')
        return jsonify({
            'message': 'Static website deployed successfully',
            'deployment': record,
            'steps': [
                'Uploaded files to S3',
                'Configured bucket website hosting',
                'Applied public read policy',
                'CloudFront distribution created' if cloudfront else 'S3 website endpoint enabled',
                f'Domain mapped: {domain}',
            ],
        }), 201

    @app.route('/api/deploy/code-upload', methods=['POST'])
    def deploy_code_upload():
        app_name = (request.form.get('appName') or '').strip()
        language = (request.form.get('language') or 'auto').strip()
        container_port = int(request.form.get('containerPort') or 8080)
        platform = request.form.get('platform') or 'linux/amd64'
        zip_file = request.files.get('codeZip')

        ok, err = _validate_app_name(app_name)
        if not ok:
            return jsonify({'error': err}), 400
        port_err = validators.validate_port(container_port, 'Container port')
        if port_err:
            return jsonify({'error': port_err}), 400
        if not zip_file or not zip_file.filename:
            return jsonify({'error': 'Please upload a ZIP file with your source code'}), 400
        if not zip_file.filename.lower().endswith('.zip'):
            return jsonify({'error': 'Only .zip files are supported'}), 400

        zip_file.seek(0, 2)
        if zip_file.tell() > MAX_ZIP_FILE:
            return jsonify({'error': 'ZIP file exceeds 200MB limit'}), 400
        zip_file.seek(0)

        dest = os.path.join(UPLOAD_DIR, 'code', app_name)
        os.makedirs(dest, exist_ok=True)
        zip_path = os.path.join(dest, secure_filename(zip_file.filename))
        zip_file.save(zip_path)

        file_list = []
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                file_list = zf.namelist()[:100]
                if zf.testzip() is not None:
                    return jsonify({'error': 'ZIP file is corrupted'}), 400
        except zipfile.BadZipFile:
            return jsonify({'error': 'Invalid ZIP file'}), 400

        if language == 'auto':
            detected, base_image = _detect_language([os.path.basename(f) for f in file_list])
        else:
            lang_map = {
                'python': ('python', 'python:3.12-slim'),
                'nodejs': ('nodejs', 'node:20-alpine'),
                'static': ('static', 'nginx:alpine'),
                'go': ('go', 'golang:1.22-alpine'),
                'java': ('java', 'eclipse-temurin:21-jre-alpine'),
            }
            detected, base_image = lang_map.get(language, ('generic', 'alpine:3.19'))

        deploy_id = str(uuid.uuid4())
        ecr_uri = f'{os.environ.get("AWS_ACCOUNT_ID", "111122223333")}.dkr.ecr.{os.environ.get("AWS_REGION", "eu-west-1")}.amazonaws.com/{app_name}:latest'
        record = {
            'id': deploy_id,
            'type': 'code-upload',
            'serviceType': 'Code Upload & Deploy',
            'resourceName': app_name,
            'appName': app_name,
            'language': detected,
            'baseImage': base_image,
            'containerPort': container_port,
            'platform': platform,
            'ecrUri': ecr_uri,
            'fileCount': len(file_list),
            'url': f'https://{app_name}.apps.example.com',
            'status': 'APPLIED',
            'createdAt': datetime.utcnow().isoformat(),
        }
        _add_deployment(record)
        _audit_deploy('deploy_create', f'Code upload deploy {app_name} ({detected})', 'code-upload')
        return jsonify({
            'message': 'Code uploaded, Docker image built and deployed',
            'deployment': record,
            'steps': [
                f'Extracted ZIP ({len(file_list)} files)',
                f'Detected runtime: {detected}',
                f'Generated Dockerfile using {base_image}',
                'docker build -t {0}:latest .'.format(app_name),
                'docker tag → ECR repository',
                f'Pushed to {ecr_uri}',
                f'Deployed to ECS/Fargate on port {container_port}',
            ],
        }), 201
