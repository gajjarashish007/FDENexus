"""Middleware simulation: services, accounts, plan generation, YAML diffs."""
import re
import time
from datetime import datetime

SERVICES = [
    {'id': 'ec2', 'name': 'EC2 Compute', 'icon': '💻', 'category': 'compute'},
    {'id': 'dynamodb', 'name': 'DynamoDB', 'icon': '📊', 'category': 'database'},
    {'id': 'alb', 'name': 'Load Balancer', 'icon': '🔄', 'category': 'networking'},
    {'id': 's3', 'name': 'S3 Storage', 'icon': '🪣', 'category': 'storage'},
    {'id': 'asg', 'name': 'Auto Scaling', 'icon': '📈', 'category': 'compute'},
    {'id': 'acm', 'name': 'ACM Certificates', 'icon': '🔒', 'category': 'security'},
    {'id': 'vpc', 'name': 'VPC Network', 'icon': '🌐', 'category': 'networking'},
    {'id': 'rds', 'name': 'RDS Database', 'icon': '🗄️', 'category': 'database'},
    {'id': 'deploy-static', 'name': 'Static Website Deploy', 'icon': '🌐', 'category': 'deploy'},
    {'id': 'deploy-code', 'name': 'Code Upload & Docker', 'icon': '📦', 'category': 'deploy'},
    {'id': 'ecs', 'name': 'ECS Fargate', 'icon': '🚢', 'category': 'containers'},
    {'id': 'lambda', 'name': 'Lambda Function', 'icon': 'λ', 'category': 'serverless'},
]

ACCOUNTS = [
    {'id': 'prod', 'name': 'Production', 'accountId': '111122223333', 'env': 'production'},
    {'id': 'staging', 'name': 'Staging', 'accountId': '444455556666', 'env': 'staging'},
    {'id': 'dev', 'name': 'Development', 'accountId': '777788889999', 'env': 'development'},
    {'id': 'sandbox', 'name': 'Sandbox', 'accountId': '000011112222', 'env': 'sandbox'},
]

TERRAFORM_RESOURCE = {
    'ec2': 'aws_instance',
    'vpc': 'aws_vpc',
    's3': 'aws_s3_bucket',
    'dynamodb': 'aws_dynamodb_table',
    'alb': 'aws_lb',
    'asg': 'aws_autoscaling_group',
    'acm': 'aws_acm_certificate',
    'rds': 'aws_db_instance',
    'ecs': 'aws_ecs_service',
    'lambda': 'aws_lambda_function',
}


def get_services():
    return SERVICES


def get_accounts():
    return ACCOUNTS


def _account_obj(account_id):
    return next((a for a in ACCOUNTS if a['id'] == account_id), ACCOUNTS[0])


def _service_obj(service_id):
    return next((s for s in SERVICES if s['id'] == service_id), SERVICES[0])


def _parse_intent(message):
    msg = (message or '').lower()
    destructive = any(w in msg for w in ['delete', 'destroy', 'remove', 'terminate'])
    create = any(w in msg for w in ['create', 'add', 'new', 'provision'])
    scale = 'scale' in msg or 'replica' in msg
    monitoring = 'monitor' in msg
    tags = 'tag' in msg or 'default tags' in msg
    secure = any(w in msg for w in ['secure', 'encrypt', 'ssl', 'tls', 'backup'])
    update = any(w in msg for w in ['update', 'change', 'modify', 'config'])

    replicas_after = 2
    m = re.search(r'(\d+)\s*replica', msg)
    if m:
        replicas_after = int(m.group(1))
    m = re.search(r'scale\s*(?:to\s*)?(\d+)', msg)
    if m:
        replicas_after = int(m.group(1))

    instance_after = 't3.medium'
    for itype in ('t3.micro', 't3.small', 't3.medium', 't3.large', 'm5.large', 'm5.xlarge'):
        if itype.replace('.', r'\.') in msg or itype in msg:
            instance_after = itype

    return {
        'destructive': destructive,
        'create': create and not destructive,
        'scale': scale,
        'monitoring': monitoring,
        'tags': tags or 'default tags' in msg,
        'secure': secure,
        'update': update or monitoring or tags or scale,
        'replicas_after': replicas_after,
        'instance_type_after': instance_after,
    }


def _header(service, account, note=''):
    svc = service.upper().replace('-', '_')
    lines = [f'# {svc} Configuration — {account["name"]}']
    if note:
        lines.append(f'# {note}')
    lines.extend([
        'apiVersion: infra/v1',
        f'kind: {service}',
        'metadata:',
        f'  name: {service}-{account["id"]}-resource',
        f'  account: "{account["accountId"]}"',
    ])
    return lines


def _build_yaml(service, account, intent, phase):
    """phase: 'before' | 'after' | 'destroy'"""
    env = account['env']
    hdr = _header(service, account)

    if service == 'vpc':
        if phase == 'before':
            if intent['create']:
                return '\n'.join(hdr + ['  labels:', '    status: pending', 'spec:', '  _state: not-provisioned'])
            return '\n'.join(hdr + [
                f'  environment: {env}',
                'spec:',
                '  cidrBlock: 10.0.0.0/16',
                '  enableDnsHostnames: true',
                '  subnets: 2',
                '  natGateway: false',
            ])
        if phase == 'destroy':
            return '\n'.join(hdr + [
                f'  environment: {env}',
                'spec:',
                '  cidrBlock: 10.0.0.0/16',
                '  _destroy: true',
            ])
        return '\n'.join(hdr + [
            f'  environment: {env}',
            '  labels:',
            '    managed-by: smartops-portal',
            'spec:',
            '  cidrBlock: 10.0.0.0/16',
            '  enableDnsHostnames: true',
            '  enableDnsSupport: true',
            '  subnets: 4',
            '  natGateway: true',
            '  availabilityZones:',
            '    - eu-west-1a',
            '    - eu-west-1b',
            '  tags:',
            '    owner: platform-team',
            '    cost-center: CC-1001',
        ])

    if service == 's3':
        bucket = f'app-{account["id"]}-data'
        if phase == 'before':
            if intent['create']:
                return '\n'.join(hdr + ['spec:', '  _state: not-provisioned'])
            return '\n'.join(hdr + [
                f'  environment: {env}',
                'spec:',
                f'  bucketName: {bucket}',
                '  versioning: false',
                '  encryption: false',
            ])
        if phase == 'destroy':
            return '\n'.join(hdr + ['spec:', f'  bucketName: {bucket}', '  _destroy: true'])
        enc = intent['secure'] or intent['create']
        return '\n'.join(hdr + [
            f'  environment: {env}',
            'spec:',
            f'  bucketName: {bucket}',
            '  versioning: true',
            f'  encryption: {str(enc).lower()}',
            '  publicAccessBlock: true',
            '  tags:',
            '    owner: platform-team',
            '    managed-by: smartops-portal',
        ])

    if service == 'dynamodb':
        table = f'{service}_{account["id"]}_table'
        if phase == 'before':
            if intent['create']:
                return '\n'.join(hdr + ['spec:', '  _state: not-provisioned'])
            return '\n'.join(hdr + [
                f'  environment: {env}',
                'spec:',
                f'  tableName: {table}',
                '  billingMode: PROVISIONED',
                '  readCapacity: 5',
                '  writeCapacity: 5',
            ])
        if phase == 'destroy':
            return '\n'.join(hdr + ['spec:', f'  tableName: {table}', '  _destroy: true'])
        return '\n'.join(hdr + [
            f'  environment: {env}',
            'spec:',
            f'  tableName: {table}',
            '  billingMode: PAY_PER_REQUEST',
            '  partitionKey: pk (String)',
            '  sortKey: sk (String)',
            '  pointInTimeRecovery: true',
            '  tags:',
            '    owner: platform-team',
        ])

    if service == 'alb':
        if phase == 'before':
            if intent['create']:
                return '\n'.join(hdr + ['spec:', '  _state: not-provisioned'])
            return '\n'.join(hdr + [
                f'  environment: {env}',
                'spec:',
                '  scheme: internet-facing',
                '  subnets: 1',
                '  idleTimeout: 60',
            ])
        if phase == 'destroy':
            return '\n'.join(hdr + ['spec:', '  _destroy: true'])
        return '\n'.join(hdr + [
            f'  environment: {env}',
            'spec:',
            '  scheme: internet-facing',
            '  type: application',
            '  subnets: 2',
            '  idleTimeout: 60',
            '  crossZoneLoadBalancing: true',
            '  tags:',
            '    owner: platform-team',
        ])

    # Default EC2-style compute spec (ec2, asg, ecs, lambda, rds, deploy-*)
    replicas_b = 1
    replicas_a = intent['replicas_after']
    itype_b = 't3.micro'
    itype_a = intent['instance_type_after']
    mon_b = 'false'
    mon_a = 'true' if intent['monitoring'] or intent['create'] else 'false'

    if phase == 'before':
        if intent['create']:
            return '\n'.join(hdr + ['spec:', '  _state: not-provisioned'])
        if intent['destructive']:
            return '\n'.join(hdr + [
                f'  environment: {env}',
                'spec:',
                f'  replicas: 3',
                f'  instanceType: {itype_a}',
                '  enabled: true',
                '  monitoring: true',
                '  tags:',
                '    owner: platform-team',
            ])
        return '\n'.join(hdr + [
            'spec:',
            f'  replicas: {replicas_b}',
            f'  instanceType: {itype_b}',
            '  enabled: false',
        ])

    if phase == 'destroy':
        return '\n'.join(hdr + [
            f'  environment: {env}',
            'spec:',
            '  replicas: 0',
            '  enabled: false',
            '  _destroy: true',
        ])

    lines = hdr + [
        f'  environment: {env}',
        'spec:',
        f'  replicas: {replicas_a}',
        f'  instanceType: {itype_a}',
        '  enabled: true',
        f'  monitoring: {mon_a}',
    ]
    if intent['tags'] or intent['create']:
        lines.extend([
            '  tags:',
            '    owner: platform-team',
            '    managed-by: smartops-portal',
            '    cost-center: CC-1001',
        ])
    if intent['secure']:
        lines.extend([
            '  encryption:',
            '    enabled: true',
            '    kmsKey: alias/aws/default',
        ])
    return '\n'.join(lines)


def _diff_changes(before, after):
    """Simple line-based change list for UI summary."""
    b_lines = before.splitlines()
    a_lines = after.splitlines()
    b_set = set(b_lines)
    changes = []
    for line in a_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        if line not in b_set and not stripped.startswith('_'):
            if ':' in stripped:
                key = stripped.split(':')[0].strip()
                changes.append({'type': 'add', 'field': key, 'detail': stripped})
    for line in b_lines:
        stripped = line.strip()
        if '_destroy' in stripped:
            changes.append({'type': 'destroy', 'field': 'resource', 'detail': 'Marked for deletion'})
            break
    if not changes and before != after:
        changes.append({'type': 'modify', 'field': 'spec', 'detail': 'Configuration updated in-place'})
    return changes[:8]


def generate_yaml_diff(service, account, user_message):
    account_obj = account if isinstance(account, dict) else _account_obj(account)
    intent = _parse_intent(user_message)

    if intent['destructive']:
        before = _build_yaml(service, account_obj, intent, 'before')
        after = _build_yaml(service, account_obj, intent, 'destroy')
    elif intent['create']:
        before = _build_yaml(service, account_obj, intent, 'before')
        after = _build_yaml(service, account_obj, intent, 'after')
    else:
        before = _build_yaml(service, account_obj, intent, 'before')
        after = _build_yaml(service, account_obj, intent, 'after')

    changes = _diff_changes(before, after)
    if intent['create']:
        summary = f'Create new {service} resource in {account_obj["name"]}'
    elif intent['destructive']:
        summary = f'Destroy {service} resource in {account_obj["name"]}'
    elif intent['scale']:
        summary = f'Scale {service} to {intent["replicas_after"]} replicas'
    else:
        summary = f'Update {service} configuration in {account_obj["name"]}'

    return {
        'before': before,
        'after': after,
        'destructive': intent['destructive'],
        'service': service,
        'account': account_obj['id'],
        'summary': summary,
        'changes': changes,
        'intent': {k: v for k, v in intent.items() if isinstance(v, (bool, int, str))},
    }


def generate_plan_lines(service, account, user_message='', destructive=False):
    account_obj = account if isinstance(account, dict) else _account_obj(account)
    intent = _parse_intent(user_message) if user_message else {'destructive': destructive}
    if user_message:
        destructive = intent['destructive']

    ts = datetime.utcnow().strftime('%H:%M:%S')
    tf_resource = TERRAFORM_RESOURCE.get(service, f'aws_{service.replace("-", "_")}')
    resource_name = f'{service}_{account_obj["id"]}_primary'
    workspace = f'{account_obj["id"]}-{service}'

    lines = [
        f'[{ts}] Terraform v1.7.0 initialized',
        f'[{ts}] Selected workspace: {workspace}',
        f'[{ts}] Loading modules: ./modules/{service}',
        f'[{ts}] Refreshing state... [{tf_resource}.{resource_name}]',
        '',
        f'Terraform will perform the following actions in account {account_obj["accountId"]}:',
        '',
    ]

    if destructive:
        lines.extend([
            f'  # {tf_resource}.{resource_name} will be destroyed',
            f'  - resource "{tf_resource}" "{resource_name}" {{',
            f'      - name         = "{service}-{account_obj["id"]}-resource"',
            f'      - replicas     = 3 -> null',
            f'      - enabled      = true -> null',
            f'    }}',
            '',
            'Plan: 0 to add, 0 to change, 1 to destroy.',
            '⚠ WARNING: This plan contains DESTRUCTIVE changes.',
        ])
    elif intent.get('create'):
        lines.extend([
            f'  # {tf_resource}.{resource_name} will be created',
            f'  + resource "{tf_resource}" "{resource_name}" {{',
            f'      + name         = "{service}-{account_obj["id"]}-resource"',
            f'      + environment  = "{account_obj["env"]}"',
            f'      + replicas     = {intent.get("replicas_after", 2)}',
            f'      + instanceType = "{intent.get("instance_type_after", "t3.medium")}"',
            f'      + monitoring   = true',
            f'      + tags         = {{',
            f'          + owner       = "platform-team"',
            f'          + managed-by  = "smartops-portal"',
            f'        }}',
            f'    }}',
            '',
            'Plan: 1 to add, 0 to change, 0 to destroy.',
        ])
    elif service == 'vpc':
        lines.extend([
            f'  # {tf_resource}.{resource_name} will be updated in-place',
            f'  ~ resource "{tf_resource}" "{resource_name}" {{',
            f'      ~ subnets      = 2 -> 4',
            f'      ~ natGateway   = false -> true',
            f'      + tags         = {{ owner = "platform-team" }}',
            f'    }}',
            '',
            'Plan: 0 to add, 1 to change, 0 to destroy.',
        ])
    elif service == 's3':
        lines.extend([
            f'  # {tf_resource}.{resource_name} will be updated in-place',
            f'  ~ resource "{tf_resource}" "{resource_name}" {{',
            f'      ~ versioning   = false -> true',
            f'      ~ encryption   = false -> true',
            f'      + publicAccessBlock = true',
            f'    }}',
            '',
            'Plan: 0 to add, 1 to change, 0 to destroy.',
        ])
    elif service == 'dynamodb':
        lines.extend([
            f'  # {tf_resource}.{resource_name} will be updated in-place',
            f'  ~ resource "{tf_resource}" "{resource_name}" {{',
            f'      ~ billingMode  = "PROVISIONED" -> "PAY_PER_REQUEST"',
            f'      + pointInTimeRecovery = true',
            f'    }}',
            '',
            'Plan: 0 to add, 1 to change, 0 to destroy.',
        ])
    else:
        lines.extend([
            f'  # {tf_resource}.{resource_name} will be updated in-place',
            f'  ~ resource "{tf_resource}" "{resource_name}" {{',
            f'      ~ replicas     = 1 -> {intent.get("replicas_after", 2)}',
            f'      ~ instanceType = "t3.micro" -> "{intent.get("instance_type_after", "t3.medium")}"',
            f'      + monitoring   = true',
            f'      + tags         = {{ managed-by = "smartops-portal" }}',
            f'    }}',
            '',
            'Plan: 0 to add, 1 to change, 0 to destroy.',
        ])

    lines.extend(['', f'[{ts}] Plan generation complete.'])
    return lines


def stream_plan(service, account, user_message, emit_fn, delay=0.08):
    account_obj = _account_obj(account)
    intent = _parse_intent(user_message)
    lines = generate_plan_lines(service, account_obj, user_message)
    for line in lines:
        emit_fn({'type': 'plan_line', 'line': line})
        time.sleep(delay)
    emit_fn({
        'type': 'plan_complete',
        'destructive': intent['destructive'],
        'summary': next((l for l in reversed(lines) if l.startswith('Plan:')), 'Plan complete'),
    })
    return intent['destructive']


def stream_apply(service, account, emit_fn, delay=0.12):
    account_obj = _account_obj(account)
    tf_resource = TERRAFORM_RESOURCE.get(service, f'aws_{service.replace("-", "_")}')
    resource_id = f'{tf_resource}.{service}_{account_obj["id"]}_primary'

    steps = [
        f'[{datetime.utcnow().strftime("%H:%M:%S")}] Initializing Terraform apply...',
        f'Workspace: {account_obj["id"]}-{service}',
        'Running pre-apply hooks... OK',
        f'{resource_id}: Refreshing state...',
        f'{resource_id}: Modifying...',
        f'{resource_id}: Still modifying... [10s elapsed]',
        f'{resource_id}: Modifications complete after 14s [id={service}-{account_obj["id"]}-resource]',
        'Running post-apply validation...',
        'Health check passed ✓',
        '',
        'Apply complete! Resources: 1 changed, 0 added, 0 destroyed.',
    ]
    for i, step in enumerate(steps):
        emit_fn({'type': 'apply_line', 'line': step, 'progress': int((i + 1) / len(steps) * 100)})
        time.sleep(delay)
    emit_fn({'type': 'apply_complete', 'success': True})


def chat_response(user_message, service, account, history=None):
    """Generate contextual assistant reply with change preview."""
    account_obj = _account_obj(account)
    svc = _service_obj(service)
    intent = _parse_intent(user_message)
    diff = generate_yaml_diff(service, account_obj, user_message)

    bullets = []
    for ch in diff.get('changes', [])[:5]:
        icon = {'add': '➕', 'modify': '🔄', 'destroy': '⚠️'}.get(ch['type'], '•')
        bullets.append(f'{icon} `{ch["detail"]}`')

    if intent['destructive']:
        opener = (
            f"I've analyzed your request for **{svc['name']}** in **{account_obj['name']}**. "
            f"This will **destroy** existing resources."
        )
    elif intent['create']:
        opener = (
            f"Creating new **{svc['name']}** in **{account_obj['name']}** "
            f"(account `{account_obj['accountId']}`)."
        )
    elif intent['scale']:
        opener = (
            f"Scaling **{svc['name']}** in **{account_obj['name']}** "
            f"to **{intent['replicas_after']}** replicas."
        )
    else:
        opener = (
            f"Updating **{svc['name']}** in **{account_obj['name']}** based on your request."
        )

    preview = '\n'.join(bullets) if bullets else '• Configuration will be updated in-place'
    return (
        f"{opener}\n\n"
        f"**Proposed changes:**\n{preview}\n\n"
        f"→ Review the **YAML diff** on the right, then confirm to generate the Terraform plan."
    )
