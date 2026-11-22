from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO
import boto3
from botocore.exceptions import ClientError
import os
from datetime import datetime

import ssp_api
import deploy_api
import validators

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, static_folder=BASE_DIR, static_url_path='')
CORS(app, origins='*')
socketio = SocketIO(
    app,
    cors_allowed_origins='*',
    async_mode='threading',
    ping_timeout=60,
    ping_interval=25,
    allow_upgrades=False,
)
ssp_api.register_ssp_routes(app, socketio)
deploy_api.register_deploy_routes(app)

# ========== Portal UI (serve at /) ==========
@app.route('/')
def serve_portal():
    return send_from_directory(BASE_DIR, 'portal.html')

# AWS Configuration
AWS_REGION = os.environ.get('AWS_REGION', 'eu-west-1')

# Initialize AWS clients
ec2_client = boto3.client('ec2', region_name=AWS_REGION)
dynamodb_client = boto3.client('dynamodb', region_name=AWS_REGION)
dynamodb_resource = boto3.resource('dynamodb', region_name=AWS_REGION)
elbv2_client = boto3.client('elbv2', region_name=AWS_REGION)
s3_client = boto3.client('s3', region_name=AWS_REGION)
autoscaling_client = boto3.client('autoscaling', region_name=AWS_REGION)
acm_client = boto3.client('acm', region_name=AWS_REGION)

# ========== Health Check ==========
@app.route('/api/health', methods=['GET'])
def health_check():
    aws_ok = False
    aws_error = None
    try:
        ec2_client.describe_regions(RegionNames=[AWS_REGION])
        aws_ok = True
    except Exception as e:
        aws_error = str(e)

    return jsonify({
        'status': 'healthy',
        'api': 'online',
        'aws': 'connected' if aws_ok else 'disconnected',
        'awsError': aws_error,
        'region': AWS_REGION,
        'timestamp': datetime.now().isoformat(),
    }), 200


def aws_list_fallback(empty_key, empty_value, error):
    """Return empty list when AWS credentials are missing or expired."""
    return jsonify({
        empty_key: empty_value,
        'awsConnected': False,
        'message': 'AWS unavailable — configure credentials for live data',
        'error': str(error),
    }), 200

# ========== Region Management ==========
@app.route('/api/region', methods=['POST'])
def change_region():
    global AWS_REGION, ec2_client, dynamodb_client, dynamodb_resource
    global elbv2_client, s3_client, autoscaling_client, acm_client
    
    try:
        data = request.json
        new_region = data.get('region')
        
        if not new_region:
            return jsonify({'error': 'Region is required'}), 400
        
        # Update region
        AWS_REGION = new_region
        
        # Reinitialize clients with new region
        ec2_client = boto3.client('ec2', region_name=AWS_REGION)
        dynamodb_client = boto3.client('dynamodb', region_name=AWS_REGION)
        dynamodb_resource = boto3.resource('dynamodb', region_name=AWS_REGION)
        elbv2_client = boto3.client('elbv2', region_name=AWS_REGION)
        s3_client = boto3.client('s3', region_name=AWS_REGION)
        autoscaling_client = boto3.client('autoscaling', region_name=AWS_REGION)
        acm_client = boto3.client('acm', region_name=AWS_REGION)
        
        return jsonify({
            'message': 'Region changed successfully',
            'region': AWS_REGION
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/region', methods=['GET'])
def get_region():
    return jsonify({'region': AWS_REGION}), 200

# ========== EC2 Endpoints ==========

EC2_INSTANCE_TYPES_CATALOG = [
    {'type': 't2.micro',   'vcpus': 1, 'memoryGb': 1,  'category': 'free-tier', 'priceHour': 0.0116, 'freeTier': True,  'desc': 'Burstable — good for low-traffic apps'},
    {'type': 't2.small',   'vcpus': 1, 'memoryGb': 2,  'category': 'general',   'priceHour': 0.023,  'freeTier': False, 'desc': 'Small web servers & dev environments'},
    {'type': 't2.medium',  'vcpus': 2, 'memoryGb': 4,  'category': 'general',   'priceHour': 0.0464, 'freeTier': False, 'desc': 'Medium workloads with moderate traffic'},
    {'type': 't3.micro',   'vcpus': 2, 'memoryGb': 1,  'category': 'free-tier', 'priceHour': 0.0104, 'freeTier': True,  'desc': 'Newer burstable — better baseline CPU'},
    {'type': 't3.small',   'vcpus': 2, 'memoryGb': 2,  'category': 'general',   'priceHour': 0.0208, 'freeTier': False, 'desc': 'Balanced for small production apps'},
    {'type': 't3.medium',  'vcpus': 2, 'memoryGb': 4,  'category': 'general',   'priceHour': 0.0416, 'freeTier': False, 'desc': 'Popular choice for web applications'},
    {'type': 't3.large',   'vcpus': 2, 'memoryGb': 8,  'category': 'general',   'priceHour': 0.0832, 'freeTier': False, 'desc': 'More memory for app servers'},
    {'type': 'm5.large',   'vcpus': 2, 'memoryGb': 8,  'category': 'general',   'priceHour': 0.096,  'freeTier': False, 'desc': 'General purpose — consistent performance'},
    {'type': 'c5.large',   'vcpus': 2, 'memoryGb': 4,  'category': 'compute',   'priceHour': 0.085,  'freeTier': False, 'desc': 'Compute optimized — CPU-heavy tasks'},
    {'type': 'c5.xlarge',  'vcpus': 4, 'memoryGb': 8,  'category': 'compute',   'priceHour': 0.17,   'freeTier': False, 'desc': 'High-performance computing'},
    {'type': 'r5.large',   'vcpus': 2, 'memoryGb': 16, 'category': 'memory',    'priceHour': 0.126,  'freeTier': False, 'desc': 'Memory optimized — databases & caching'},
    {'type': 'r5.xlarge',  'vcpus': 4, 'memoryGb': 32, 'category': 'memory',    'priceHour': 0.252,  'freeTier': False, 'desc': 'Large in-memory workloads'},
]

EC2_AMIS_CATALOG = [
    {'id': 'ami-0fa07a22bf678ff97', 'name': 'Amazon Linux 2023 (latest)', 'os': 'amazon-linux', 'architecture': 'x86_64', 'rootDevice': 'ebs', 'description': 'Amazon Linux 2023 — recommended for most workloads'},
    {'id': 'ami-0c55b159cbfafe1f0', 'name': 'Amazon Linux 2 (HVM)', 'os': 'amazon-linux', 'architecture': 'x86_64', 'rootDevice': 'ebs', 'description': 'Amazon Linux 2 — widely used stable image'},
    {'id': 'ami-0e731c8a588258d0d', 'name': 'Ubuntu Server 22.04 LTS', 'os': 'ubuntu', 'architecture': 'x86_64', 'rootDevice': 'ebs', 'description': 'Ubuntu 22.04 LTS — popular open-source OS'},
    {'id': 'ami-0a0c8eebcdd6dc329', 'name': 'Ubuntu Server 20.04 LTS', 'os': 'ubuntu', 'architecture': 'x86_64', 'rootDevice': 'ebs', 'description': 'Ubuntu 20.04 LTS — long-term support'},
    {'id': 'ami-0a8e0333a3e0322a2', 'name': 'Windows Server 2022 Base', 'os': 'windows', 'architecture': 'x86_64', 'rootDevice': 'ebs', 'description': 'Windows Server 2022 — .NET & IIS workloads'},
    {'id': 'ami-0df368112825f8a8f', 'name': 'Windows Server 2019 Base', 'os': 'windows', 'architecture': 'x86_64', 'rootDevice': 'ebs', 'description': 'Windows Server 2019 — legacy Windows apps'},
]


def _format_instance_type(it):
    monthly = round(it['priceHour'] * 730, 2)
    return {
        **it,
        'priceMonth': monthly,
        'priceLabel': 'Free Tier eligible' if it.get('freeTier') else f"${it['priceHour']:.4f}/hr",
        'priceDetail': '(750 hrs/mo free for 12 months)' if it.get('freeTier') else f'~${monthly}/month estimated',
    }


@app.route('/api/ec2/instance-types', methods=['GET'])
def list_ec2_instance_types():
    category = request.args.get('category', 'all')
    types = [_format_instance_type(dict(t)) for t in EC2_INSTANCE_TYPES_CATALOG]
    if category == 'free-tier':
        types = [t for t in types if t.get('freeTier')]
    elif category and category != 'all':
        types = [t for t in types if t['category'] == category]
    aws_connected = False
    try:
        ec2_client.describe_instance_types(InstanceTypes=['t3.micro'])
        aws_connected = True
    except Exception:
        pass
    return jsonify({'instanceTypes': types, 'awsConnected': aws_connected}), 200


@app.route('/api/ec2/amis', methods=['GET'])
def list_ec2_amis():
    os_filter = request.args.get('os', 'all')
    amis = []
    aws_connected = False
    try:
        filters = [{'Name': 'state', 'Values': ['available']}, {'Name': 'architecture', 'Values': ['x86_64']}]
        owners = ['amazon']
        name_patterns = {
            'amazon-linux': ['amzn2-ami-hvm-*-x86_64-gp2', 'al2023-ami-*-x86_64'],
            'ubuntu': ['ubuntu/images/hvm-ssd/ubuntu-jammy*', 'ubuntu/images/hvm-ssd/ubuntu-focal*'],
            'windows': ['Windows_Server-2022-English-Full-Base*', 'Windows_Server-2019-English-Full-Base*'],
        }
        if os_filter in name_patterns:
            for pattern in name_patterns[os_filter]:
                if os_filter == 'ubuntu':
                    owners = ['099720109477']
                else:
                    owners = ['amazon']
                resp = ec2_client.describe_images(
                    Owners=owners,
                    Filters=filters + [{'Name': 'name', 'Values': [pattern]}],
                )
                for img in sorted(resp.get('Images', []), key=lambda x: x['CreationDate'], reverse=True)[:3]:
                    os_name = os_filter
                    if 'Windows' in img.get('Name', ''):
                        os_name = 'windows'
                    elif 'ubuntu' in img.get('Name', '').lower():
                        os_name = 'ubuntu'
                    elif 'amzn' in img.get('Name', '').lower() or 'al2023' in img.get('Name', '').lower():
                        os_name = 'amazon-linux'
                    amis.append({
                        'id': img['ImageId'],
                        'name': img.get('Name', img['ImageId']),
                        'os': os_name,
                        'architecture': img.get('Architecture', 'x86_64'),
                        'rootDevice': img.get('RootDeviceType', 'ebs'),
                        'description': img.get('Description', '')[:120] or img.get('Name', ''),
                        'creationDate': img.get('CreationDate', ''),
                    })
        aws_connected = True
        seen = set()
        unique = []
        for a in amis:
            if a['id'] not in seen:
                seen.add(a['id'])
                unique.append(a)
        amis = unique
    except Exception:
        amis = [dict(a) for a in EC2_AMIS_CATALOG]

    if not amis:
        amis = [dict(a) for a in EC2_AMIS_CATALOG]

    if os_filter and os_filter != 'all':
        amis = [a for a in amis if a.get('os') == os_filter]

    return jsonify({'amis': amis, 'awsConnected': aws_connected}), 200


@app.route('/api/ec2/key-pairs', methods=['GET'])
def list_ec2_key_pairs():
    try:
        resp = ec2_client.describe_key_pairs()
        keys = [{'name': k['KeyName'], 'id': k.get('KeyPairId', ''), 'type': k.get('KeyType', 'rsa')} for k in resp.get('KeyPairs', [])]
        return jsonify({'keyPairs': keys, 'awsConnected': True}), 200
    except Exception as e:
        return jsonify({
            'keyPairs': [],
            'awsConnected': False,
            'message': 'Enter key pair name manually if not listed',
            'error': str(e),
        }), 200


@app.route('/api/ec2/instances', methods=['GET'])
def list_ec2_instances():
    try:
        response = ec2_client.describe_instances()
        instances = []
        
        for reservation in response.get('Reservations', []):
            for instance in reservation.get('Instances', []):
                # Get instance name from tags
                name = ''
                for tag in instance.get('Tags', []):
                    if tag['Key'] == 'Name':
                        name = tag['Value']
                        break
                
                instances.append({
                    'instanceId': instance['InstanceId'],
                    'name': name,
                    'instanceType': instance['InstanceType'],
                    'state': instance['State']['Name'],
                    'publicIp': instance.get('PublicIpAddress', ''),
                    'privateIp': instance.get('PrivateIpAddress', ''),
                    'launchTime': instance['LaunchTime'].isoformat()
                })
        
        return jsonify({'instances': instances}), 200
    except ClientError as e:
        return aws_list_fallback('instances', [], e)
    except Exception as e:
        return aws_list_fallback('instances', [], e)

@app.route('/api/ec2/instances', methods=['POST'])
def launch_ec2_instance():
    try:
        data = request.json
        instance_name = data.get('instanceName', '')
        ami_id = data.get('amiId')
        instance_type = data.get('instanceType', 't2.micro')
        key_name = data.get('keyName')
        
        if not ami_id:
            return jsonify({'error': 'AMI ID is required'}), 400

        err = validators.validate_ami_id(ami_id)
        if err:
            return jsonify({'error': err}), 400
        if instance_name and not validators.KEY_NAME_RE.match(instance_name):
            return jsonify({'error': 'Invalid instance name format'}), 400
        
        params = {
            'ImageId': ami_id,
            'InstanceType': instance_type,
            'MinCount': 1,
            'MaxCount': 1
        }
        
        if key_name:
            params['KeyName'] = key_name
        
        if instance_name:
            params['TagSpecifications'] = [{
                'ResourceType': 'instance',
                'Tags': [{'Key': 'Name', 'Value': instance_name}]
            }]
        
        response = ec2_client.run_instances(**params)
        
        return jsonify({
            'message': 'Instance launched successfully',
            'instanceId': response['Instances'][0]['InstanceId']
        }), 201
    except ClientError as e:
        return jsonify({'error': str(e)}), 500



# ========== DynamoDB Endpoints ==========

@app.route('/api/dynamodb/tables', methods=['GET'])
def list_dynamodb_tables():
    try:
        response = dynamodb_client.list_tables()
        table_names = response.get('TableNames', [])
        
        if not table_names:
            return jsonify({'tables': []}), 200
        
        tables = []
        for table_name in table_names:
            table_info = dynamodb_client.describe_table(TableName=table_name)
            table = table_info['Table']
            
            tables.append({
                'tableName': table['TableName'],
                'status': table['TableStatus'],
                'itemCount': table.get('ItemCount', 0),
                'tableSizeBytes': table.get('TableSizeBytes', 0),
                'creationDateTime': table['CreationDateTime'].isoformat()
            })
        
        return jsonify({'tables': tables}), 200
    except ClientError as e:
        return aws_list_fallback('tables', [], e)
    except Exception as e:
        return aws_list_fallback('tables', [], e)

@app.route('/api/dynamodb/tables', methods=['POST'])
def create_dynamodb_table():
    try:
        data = request.json
        table_name = data.get('tableName')
        partition_key = data.get('partitionKey')
        partition_key_type = data.get('partitionKeyType', 'S')
        sort_key = data.get('sortKey')
        sort_key_type = data.get('sortKeyType', 'S')
        billing_mode = data.get('billingMode', 'PAY_PER_REQUEST')
        
        if not all([table_name, partition_key]):
            return jsonify({'error': 'Table name and partition key are required'}), 400

        err = validators.validate_dynamodb_table(
            table_name, partition_key, sort_key, partition_key_type, sort_key_type
        )
        if err:
            return jsonify({'error': err}), 400
        
        key_schema = [{'AttributeName': partition_key, 'KeyType': 'HASH'}]
        attribute_definitions = [{'AttributeName': partition_key, 'AttributeType': partition_key_type}]
        
        if sort_key:
            key_schema.append({'AttributeName': sort_key, 'KeyType': 'RANGE'})
            attribute_definitions.append({'AttributeName': sort_key, 'AttributeType': sort_key_type})
        
        params = {
            'TableName': table_name,
            'KeySchema': key_schema,
            'AttributeDefinitions': attribute_definitions,
            'BillingMode': billing_mode
        }
        
        response = dynamodb_client.create_table(**params)
        
        return jsonify({
            'message': 'Table created successfully',
            'table': response['TableDescription']
        }), 201
    except ClientError as e:
        return jsonify({'error': str(e)}), 500



# ========== ALB Endpoints ==========

@app.route('/api/alb/load-balancers', methods=['GET'])
def list_load_balancers():
    try:
        response = elbv2_client.describe_load_balancers()
        load_balancers = []
        
        for lb in response.get('LoadBalancers', []):
            load_balancers.append({
                'name': lb['LoadBalancerName'],
                'arn': lb['LoadBalancerArn'],
                'dnsName': lb['DNSName'],
                'state': lb['State']['Code'],
                'type': lb['Type'],
                'scheme': lb['Scheme'],
                'createdTime': lb['CreatedTime'].isoformat()
            })
        
        return jsonify({'loadBalancers': load_balancers}), 200
    except ClientError as e:
        return aws_list_fallback('loadBalancers', [], e)
    except Exception as e:
        return aws_list_fallback('loadBalancers', [], e)

@app.route('/api/alb/load-balancers', methods=['POST'])
def create_load_balancer():
    try:
        data = request.json
        name = data.get('name')
        subnets = data.get('subnets', [])
        scheme = data.get('scheme', 'internet-facing')
        lb_type = data.get('type', 'application')
        
        if not name or not subnets:
            return jsonify({'error': 'Name and subnets are required'}), 400

        err = validators.validate_subnet_ids(subnets)
        if err:
            return jsonify({'error': err}), 400
        if not validators.ASG_NAME_RE.match(name):
            return jsonify({'error': 'Invalid load balancer name format'}), 400
        
        response = elbv2_client.create_load_balancer(
            Name=name,
            Subnets=subnets,
            Scheme=scheme,
            Type=lb_type,
            IpAddressType='ipv4'
        )
        
        return jsonify({
            'message': 'Load balancer created successfully',
            'loadBalancer': response['LoadBalancers'][0]
        }), 201
    except ClientError as e:
        return jsonify({'error': str(e)}), 500

# ========== S3 Endpoints ==========

@app.route('/api/s3/buckets', methods=['GET'])
def list_s3_buckets():
    try:
        response = s3_client.list_buckets()
        buckets = []
        
        for bucket in response.get('Buckets', []):
            bucket_name = bucket['Name']
            
            # Get bucket location
            try:
                location = s3_client.get_bucket_location(Bucket=bucket_name)
                region = location.get('LocationConstraint') or 'us-east-1'
            except:
                region = 'unknown'
            
            buckets.append({
                'name': bucket_name,
                'creationDate': bucket['CreationDate'].isoformat(),
                'region': region
            })
        
        return jsonify({'buckets': buckets}), 200
    except ClientError as e:
        return aws_list_fallback('buckets', [], e)
    except Exception as e:
        return aws_list_fallback('buckets', [], e)

@app.route('/api/s3/buckets', methods=['POST'])
def create_s3_bucket():
    try:
        data = request.json
        bucket_name = data.get('bucketName')
        enable_website = data.get('enableWebsite', False)
        
        if not bucket_name:
            return jsonify({'error': 'Bucket name is required'}), 400

        err = validators.validate_s3_bucket(bucket_name)
        if err:
            return jsonify({'error': err}), 400
        
        # Create bucket
        if AWS_REGION == 'us-east-1':
            s3_client.create_bucket(Bucket=bucket_name)
        else:
            s3_client.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={'LocationConstraint': AWS_REGION}
            )
        
        # Enable static website hosting if requested
        if enable_website:
            s3_client.put_bucket_website(
                Bucket=bucket_name,
                WebsiteConfiguration={
                    'IndexDocument': {'Suffix': 'index.html'},
                    'ErrorDocument': {'Key': 'error.html'}
                }
            )
            
            # Make bucket public for website
            s3_client.put_bucket_policy(
                Bucket=bucket_name,
                Policy=f'''{{
                    "Version": "2012-10-17",
                    "Statement": [{{
                        "Sid": "PublicReadGetObject",
                        "Effect": "Allow",
                        "Principal": "*",
                        "Action": "s3:GetObject",
                        "Resource": "arn:aws:s3:::{bucket_name}/*"
                    }}]
                }}'''
            )
        
        return jsonify({
            'message': 'S3 bucket created successfully',
            'bucketName': bucket_name,
            'websiteEnabled': enable_website
        }), 201
    except ClientError as e:
        return jsonify({'error': str(e)}), 500

# ========== ASG Endpoints ==========

LAUNCH_TEMPLATES_CATALOG = [
    {'name': 'my-launch-template', 'id': 'lt-0webserver001', 'version': 1, 'amiId': 'ami-0fa07a22bf678ff97', 'instanceType': 't3.micro', 'description': 'Amazon Linux 2023 — web server default'},
    {'name': 'api-server-template', 'id': 'lt-0apiserver01', 'version': 2, 'amiId': 'ami-0c55b159cbfafe1f0', 'instanceType': 't3.small', 'description': 'Amazon Linux 2 — API backend'},
    {'name': 'worker-template', 'id': 'lt-0worker0001', 'version': 1, 'amiId': 'ami-0e731c8a588258d0d', 'instanceType': 't3.medium', 'description': 'Ubuntu 22.04 — background workers'},
]

SUBNETS_CATALOG = [
    {'id': 'subnet-0a1b2c3d', 'name': 'Public Subnet A', 'az': 'eu-west-1a', 'cidr': '10.0.1.0/24', 'vpcId': 'vpc-default', 'public': True},
    {'id': 'subnet-0e4f5g6h', 'name': 'Public Subnet B', 'az': 'eu-west-1b', 'cidr': '10.0.2.0/24', 'vpcId': 'vpc-default', 'public': True},
    {'id': 'subnet-0i7j8k9l', 'name': 'Private Subnet A', 'az': 'eu-west-1a', 'cidr': '10.0.3.0/24', 'vpcId': 'vpc-default', 'public': False},
    {'id': 'subnet-0m0n1o2p', 'name': 'Private Subnet B', 'az': 'eu-west-1b', 'cidr': '10.0.4.0/24', 'vpcId': 'vpc-default', 'public': False},
]


@app.route('/api/ec2/subnets', methods=['GET'])
def list_ec2_subnets():
    subnets = []
    aws_connected = False
    try:
        resp = ec2_client.describe_subnets()
        for sn in resp.get('Subnets', []):
            name = sn['SubnetId']
            for tag in sn.get('Tags', []):
                if tag['Key'] == 'Name':
                    name = tag['Value']
                    break
            subnets.append({
                'id': sn['SubnetId'],
                'name': name,
                'az': sn['AvailabilityZone'],
                'cidr': sn.get('CidrBlock', ''),
                'vpcId': sn.get('VpcId', ''),
                'public': sn.get('MapPublicIpOnLaunch', False),
            })
        aws_connected = True
    except Exception:
        subnets = [dict(s) for s in SUBNETS_CATALOG]

    if not subnets:
        subnets = [dict(s) for s in SUBNETS_CATALOG]

    return jsonify({'subnets': subnets, 'awsConnected': aws_connected}), 200


@app.route('/api/asg/launch-templates', methods=['GET'])
def list_launch_templates():
    templates = []
    aws_connected = False
    try:
        resp = ec2_client.describe_launch_templates()
        for lt in resp.get('LaunchTemplates', []):
            detail = {'name': lt['LaunchTemplateName'], 'id': lt['LaunchTemplateId'], 'version': lt.get('LatestVersionNumber', 1)}
            try:
                ver = ec2_client.describe_launch_template_versions(
                    LaunchTemplateId=lt['LaunchTemplateId'],
                    Versions=[str(lt.get('LatestVersionNumber', 1))],
                )
                data = ver['LaunchTemplateVersions'][0]['LaunchTemplateData']
                detail['amiId'] = data.get('ImageId', '')
                detail['instanceType'] = data.get('InstanceType', '')
                detail['description'] = f"{detail.get('instanceType', 'unknown')} · {detail.get('amiId', 'ami')}"
            except Exception:
                detail['description'] = 'Launch template'
            templates.append(detail)
        aws_connected = True
    except Exception:
        templates = [dict(t) for t in LAUNCH_TEMPLATES_CATALOG]

    if not templates:
        templates = [dict(t) for t in LAUNCH_TEMPLATES_CATALOG]

    return jsonify({'launchTemplates': templates, 'awsConnected': aws_connected}), 200


@app.route('/api/asg/groups', methods=['GET'])
def list_auto_scaling_groups():
    try:
        response = autoscaling_client.describe_auto_scaling_groups()
        groups = []
        
        for asg in response.get('AutoScalingGroups', []):
            groups.append({
                'name': asg['AutoScalingGroupName'],
                'minSize': asg['MinSize'],
                'maxSize': asg['MaxSize'],
                'desiredCapacity': asg['DesiredCapacity'],
                'instanceCount': len(asg.get('Instances', [])),
                'healthCheckType': asg['HealthCheckType'],
                'createdTime': asg['CreatedTime'].isoformat()
            })
        
        return jsonify({'autoScalingGroups': groups}), 200
    except ClientError as e:
        return aws_list_fallback('autoScalingGroups', [], e)
    except Exception as e:
        return aws_list_fallback('autoScalingGroups', [], e)

@app.route('/api/asg/groups', methods=['POST'])
def create_auto_scaling_group():
    try:
        data = request.json
        name = data.get('name')
        launch_template = data.get('launchTemplate')
        min_size = data.get('minSize', 1)
        max_size = data.get('maxSize', 3)
        desired_capacity = data.get('desiredCapacity', 2)
        subnets = data.get('subnets', [])
        
        if not all([name, launch_template, subnets]):
            return jsonify({'error': 'Missing required fields'}), 400

        err = validators.validate_asg(name, min_size, desired_capacity, max_size)
        if err:
            return jsonify({'error': err}), 400
        err = validators.validate_subnet_ids(subnets)
        if err:
            return jsonify({'error': err}), 400
        
        response = autoscaling_client.create_auto_scaling_group(
            AutoScalingGroupName=name,
            LaunchTemplate={'LaunchTemplateName': launch_template},
            MinSize=min_size,
            MaxSize=max_size,
            DesiredCapacity=desired_capacity,
            VPCZoneIdentifier=','.join(subnets),
            HealthCheckType='EC2',
            HealthCheckGracePeriod=300
        )
        
        return jsonify({
            'message': 'Auto Scaling Group created successfully',
            'name': name
        }), 201
    except ClientError as e:
        return jsonify({'error': str(e)}), 500

# ========== ACM Endpoints ==========

@app.route('/api/acm/certificates', methods=['GET'])
def list_certificates():
    try:
        response = acm_client.list_certificates()
        certificates = []
        
        for cert in response.get('CertificateSummaryList', []):
            cert_arn = cert['CertificateArn']
            
            # Get detailed certificate info
            detail = acm_client.describe_certificate(CertificateArn=cert_arn)
            cert_detail = detail['Certificate']
            
            certificates.append({
                'domainName': cert_detail['DomainName'],
                'arn': cert_arn,
                'status': cert_detail['Status'],
                'type': cert_detail.get('Type', 'AMAZON_ISSUED'),
                'createdAt': cert_detail.get('CreatedAt', '').isoformat() if cert_detail.get('CreatedAt') else ''
            })
        
        return jsonify({'certificates': certificates}), 200
    except ClientError as e:
        return aws_list_fallback('certificates', [], e)
    except Exception as e:
        return aws_list_fallback('certificates', [], e)

@app.route('/api/acm/certificates', methods=['POST'])
def request_certificate():
    try:
        data = request.json
        domain_name = data.get('domainName')
        validation_method = data.get('validationMethod', 'DNS')
        
        if not domain_name:
            return jsonify({'error': 'Domain name is required'}), 400

        err = validators.validate_acm_domain(domain_name)
        if err:
            return jsonify({'error': err}), 400
        
        response = acm_client.request_certificate(
            DomainName=domain_name,
            ValidationMethod=validation_method,
            SubjectAlternativeNames=[domain_name, f'*.{domain_name}']
        )
        
        return jsonify({
            'message': 'Certificate requested successfully',
            'certificateArn': response['CertificateArn']
        }), 201
    except ClientError as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print(f"Starting AWS Cloud Dashboard API on http://localhost:5000")
    print(f"AWS Region: {AWS_REGION}")
    print("SmartOps Portal: http://localhost:5000")
    print("Auth: sign up via portal; admin approves new users before login")
    print("Available endpoints:")
    print("  Auth:")
    print("    - POST /api/auth/signup")
    print("    - POST /api/auth/login")
    print("    - GET  /api/auth/me")
    print("    - GET  /api/auth/pending-users  (admin)")
    print("    - POST /api/auth/users/<id>/approve  (admin)")
    print("    - POST /api/auth/users/<id>/reject  (admin)")
    print("  Middleware:")
    print("    - GET  /api/middleware/services")
    print("    - GET  /api/middleware/accounts")
    print("  SSP:")
    print("    - POST /api/chat/stream")
    print("    - POST /api/plan/yaml-diff")
    print("    - GET  /api/pr/status")
    print("    - GET  /api/logs")
    print("    - WS   generate_plan / apply_plan")
    print("  EC2:")
    print("    - GET  /api/ec2/instance-types")
    print("    - GET  /api/ec2/amis")
    print("    - GET  /api/ec2/key-pairs")
    print("    - GET  /api/ec2/instances")
    print("    - POST /api/ec2/instances")
    print("  DynamoDB:")
    print("    - GET  /api/dynamodb/tables")
    print("    - POST /api/dynamodb/tables")
    print("  ALB:")
    print("    - GET  /api/alb/load-balancers")
    print("    - POST /api/alb/load-balancers")
    print("  S3:")
    print("    - GET  /api/s3/buckets")
    print("    - POST /api/s3/buckets")
    print("  ASG:")
    print("    - GET  /api/asg/launch-templates")
    print("    - GET  /api/ec2/subnets")
    print("    - GET  /api/asg/groups")
    print("    - POST /api/asg/groups")
    print("  ACM:")
    print("    - GET  /api/acm/certificates")
    print("    - POST /api/acm/certificates")
    socketio.run(app, debug=True, host='0.0.0.0', port=5000, allow_unsafe_werkzeug=True)
