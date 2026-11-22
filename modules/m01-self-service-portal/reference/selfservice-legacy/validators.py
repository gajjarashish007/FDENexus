"""Server-side input validation for AWS API endpoints."""
import re

APP_NAME_RE = re.compile(r'^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$')
DOMAIN_RE = re.compile(r'^([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$')
S3_BUCKET_RE = re.compile(r'^[a-z0-9]([a-z0-9.-]{1,61}[a-z0-9])?$')
AMI_ID_RE = re.compile(r'^ami-[a-f0-9]{8,17}$', re.I)
SUBNET_ID_RE = re.compile(r'^subnet-[a-f0-9]{8,17}$', re.I)
TABLE_NAME_RE = re.compile(r'^[a-zA-Z0-9_.-]{3,255}$')
KEY_NAME_RE = re.compile(r'^[a-zA-Z0-9_.-]{1,255}$')
ASG_NAME_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9-]*$')
DDB_KEY_TYPES = frozenset({'S', 'N', 'B'})


def validate_app_name(name):
    if not name or not APP_NAME_RE.match(name):
        return 'Application name must be lowercase letters, numbers, hyphens (3–63 chars)'
    if len(name) < 3:
        return 'Application name must be at least 3 characters'
    return None


def validate_domain(domain):
    if not domain or not DOMAIN_RE.match(domain):
        return 'Invalid domain format (e.g. app.example.com)'
    return None


def validate_s3_bucket(name):
    if not name or len(name) < 3 or len(name) > 63:
        return 'Bucket name must be 3–63 characters'
    if not S3_BUCKET_RE.match(name):
        return 'Bucket name: lowercase letters, numbers, dots, hyphens only'
    if '..' in name:
        return 'Bucket name cannot contain consecutive dots'
    return None


def validate_ami_id(ami_id):
    if not ami_id or not AMI_ID_RE.match(ami_id):
        return 'Invalid AMI ID format (expected ami-xxxxxxxx)'
    return None


def validate_subnet_ids(subnet_ids):
    if not subnet_ids:
        return 'At least one subnet ID is required'
    for sid in subnet_ids:
        if not SUBNET_ID_RE.match(sid):
            return f'Invalid subnet ID: {sid}'
    return None


def validate_dynamodb_table(table_name, partition_key, sort_key=None,
                            partition_key_type='S', sort_key_type='S'):
    if not table_name or not TABLE_NAME_RE.match(table_name):
        return 'Table name must be 3–255 chars (letters, numbers, underscore, dot, hyphen)'
    if not partition_key or not KEY_NAME_RE.match(partition_key):
        return 'Invalid partition key name'
    if partition_key_type not in DDB_KEY_TYPES:
        return 'Partition key type must be S, N, or B'
    if sort_key:
        if not KEY_NAME_RE.match(sort_key):
            return 'Invalid sort key name'
        if sort_key == partition_key:
            return 'Sort key must differ from partition key'
        if sort_key_type not in DDB_KEY_TYPES:
            return 'Sort key type must be S, N, or B'
    return None


def validate_asg(name, min_size, desired, max_size):
    if not name or not ASG_NAME_RE.match(name):
        return 'ASG name: letters, numbers, hyphens; must start with letter or number'
    try:
        min_size, desired, max_size = int(min_size), int(desired), int(max_size)
    except (TypeError, ValueError):
        return 'Capacity values must be integers'
    if min_size > desired:
        return 'Minimum capacity cannot exceed desired capacity'
    if desired > max_size:
        return 'Desired capacity cannot exceed maximum capacity'
    return None


def validate_acm_domain(domain):
    if not domain:
        return 'Domain name is required'
    check = domain[2:] if domain.startswith('*.') else domain
    if not DOMAIN_RE.match(check):
        return 'Invalid domain format'
    return None


def validate_port(port, label='Port'):
    try:
        port = int(port)
    except (TypeError, ValueError):
        return f'{label} must be a number'
    if port < 1 or port > 65535:
        return f'{label} must be between 1 and 65535'
    return None
