# AWS Connection Guide

## 🔐 Two Ways to Connect to AWS

### Method 1: IAM Access Keys (Recommended for Development)

**Step 1: Create IAM User**
1. Go to AWS Console → IAM → Users
2. Click "Add users"
3. Enter username (e.g., `dashboard-user`)
4. Select "Access key - Programmatic access"
5. Click "Next: Permissions"

**Step 2: Attach Policies**
Attach these managed policies:
- `AmazonEC2FullAccess`
- `AmazonDynamoDBFullAccess`
- `AmazonS3FullAccess`
- `ElasticLoadBalancingFullAccess`
- `AutoScalingFullAccess`
- `AWSCertificateManagerFullAccess`

Or create custom policy with minimal permissions:
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ec2:Describe*",
                "ec2:RunInstances",
                "ec2:CreateTags",
                "elasticloadbalancing:Describe*",
                "elasticloadbalancing:Create*",
                "dynamodb:List*",
                "dynamodb:Describe*",
                "dynamodb:CreateTable",
                "s3:List*",
                "s3:CreateBucket",
                "s3:PutBucket*",
                "autoscaling:Describe*",
                "autoscaling:CreateAutoScalingGroup",
                "acm:List*",
                "acm:Describe*",
                "acm:RequestCertificate"
            ],
            "Resource": "*"
        }
    ]
}
```

**Step 3: Get Access Keys**
1. Click "Create access key"
2. Download CSV file or copy keys
3. **IMPORTANT**: Save keys securely, you won't see them again!

**Step 4: Configure Dashboard**

**Option A: AWS CLI Configuration**
```bash
aws configure
# AWS Access Key ID: YOUR_ACCESS_KEY
# AWS Secret Access Key: YOUR_SECRET_KEY
# Default region name: us-east-1
# Default output format: json
```

**Option B: Environment Variables**
```bash
# Windows
set AWS_ACCESS_KEY_ID=YOUR_ACCESS_KEY
set AWS_SECRET_ACCESS_KEY=YOUR_SECRET_KEY
set AWS_DEFAULT_REGION=us-east-1

# Linux/Mac
export AWS_ACCESS_KEY_ID=YOUR_ACCESS_KEY
export AWS_SECRET_ACCESS_KEY=YOUR_SECRET_KEY
export AWS_DEFAULT_REGION=us-east-1
```

**Option C: Credentials File**
Create/edit `~/.aws/credentials`:
```ini
[default]
aws_access_key_id = YOUR_ACCESS_KEY
aws_secret_access_key = YOUR_SECRET_KEY
```

Create/edit `~/.aws/config`:
```ini
[default]
region = us-east-1
output = json
```

---

### Method 2: IAM Role (Recommended for Production/EC2)

**When to Use:**
- Running dashboard on EC2 instance
- Production environments
- Better security (no long-term credentials)

**Step 1: Create IAM Role**
1. Go to AWS Console → IAM → Roles
2. Click "Create role"
3. Select "AWS service" → "EC2"
4. Click "Next: Permissions"

**Step 2: Attach Policies**
Same policies as Method 1:
- `AmazonEC2FullAccess`
- `AmazonDynamoDBFullAccess`
- `AmazonS3FullAccess`
- `ElasticLoadBalancingFullAccess`
- `AutoScalingFullAccess`
- `AWSCertificateManagerFullAccess`

**Step 3: Name the Role**
- Role name: `DashboardEC2Role`
- Description: "Role for AWS Cloud Dashboard"
- Click "Create role"

**Step 4: Attach Role to EC2**
1. Go to EC2 Console
2. Select your instance
3. Actions → Security → Modify IAM role
4. Select `DashboardEC2Role`
5. Click "Update IAM role"

**Step 5: No Configuration Needed!**
- Dashboard automatically uses instance role
- No credentials to manage
- Credentials rotate automatically

---

## 🔍 Fetching AWS Resources

### Get Available AMIs

**Method 1: AWS CLI**
```bash
# List Amazon Linux 2 AMIs
aws ec2 describe-images \
    --owners amazon \
    --filters "Name=name,Values=amzn2-ami-hvm-*-x86_64-gp2" \
    --query 'Images[*].[ImageId,Name,CreationDate]' \
    --output table

# List Ubuntu AMIs
aws ec2 describe-images \
    --owners 099720109477 \
    --filters "Name=name,Values=ubuntu/images/hvm-ssd/ubuntu-*-amd64-server-*" \
    --query 'Images[*].[ImageId,Name,CreationDate]' \
    --output table
```

**Method 2: Dashboard API**
Add to `backend-api.py`:
```python
@app.route('/api/ec2/amis', methods=['GET'])
def list_amis():
    try:
        response = ec2_client.describe_images(
            Owners=['amazon'],
            Filters=[
                {'Name': 'name', 'Values': ['amzn2-ami-hvm-*-x86_64-gp2']},
                {'Name': 'state', 'Values': ['available']}
            ]
        )
        
        amis = []
        for image in response['Images'][:20]:  # Limit to 20
            amis.append({
                'id': image['ImageId'],
                'name': image['Name'],
                'description': image.get('Description', ''),
                'creationDate': image['CreationDate']
            })
        
        return jsonify({'amis': amis}), 200
    except ClientError as e:
        return jsonify({'error': str(e)}), 500
```

### Get VPCs and Subnets

```bash
# List VPCs
aws ec2 describe-vpcs --query 'Vpcs[*].[VpcId,CidrBlock,IsDefault]' --output table

# List Subnets
aws ec2 describe-subnets --query 'Subnets[*].[SubnetId,VpcId,CidrBlock,AvailabilityZone]' --output table
```

### Get Security Groups

```bash
# List Security Groups
aws ec2 describe-security-groups --query 'SecurityGroups[*].[GroupId,GroupName,Description]' --output table
```

### Get Key Pairs

```bash
# List Key Pairs
aws ec2 describe-key-pairs --query 'KeyPairs[*].[KeyName,KeyPairId]' --output table
```

### Get Instance Types

```bash
# List available instance types
aws ec2 describe-instance-types \
    --filters "Name=instance-type,Values=t2.*,t3.*" \
    --query 'InstanceTypes[*].[InstanceType,VCpuInfo.DefaultVCpus,MemoryInfo.SizeInMiB]' \
    --output table
```

---

## 🏗️ Terraform Integration

### Generate Terraform Code

The dashboard can generate Terraform code for resources you create.

**Example: EC2 Instance Terraform**
```hcl
# main.tf
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

resource "aws_instance" "web_server" {
  ami           = "ami-0c55b159cbfafe1f0"
  instance_type = "t2.micro"
  
  tags = {
    Name = "my-web-server"
    ManagedBy = "AWS-Cloud-Dashboard"
  }
}

output "instance_id" {
  value = aws_instance.web_server.id
}

output "public_ip" {
  value = aws_instance.web_server.public_ip
}
```

**Example: DynamoDB Table Terraform**
```hcl
resource "aws_dynamodb_table" "my_table" {
  name           = "my-table"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "id"
  
  attribute {
    name = "id"
    type = "S"
  }
  
  tags = {
    Name = "my-table"
    ManagedBy = "AWS-Cloud-Dashboard"
  }
}
```

**Example: S3 Bucket Terraform**
```hcl
resource "aws_s3_bucket" "my_bucket" {
  bucket = "my-unique-bucket-name"
  
  tags = {
    Name = "my-bucket"
    ManagedBy = "AWS-Cloud-Dashboard"
  }
}

resource "aws_s3_bucket_website_configuration" "my_bucket_website" {
  bucket = aws_s3_bucket.my_bucket.id
  
  index_document {
    suffix = "index.html"
  }
  
  error_document {
    key = "error.html"
  }
}

resource "aws_s3_bucket_public_access_block" "my_bucket_public" {
  bucket = aws_s3_bucket.my_bucket.id
  
  block_public_acls       = false
  block_public_policy     = false
  ignore_public_acls      = false
  restrict_public_buckets = false
}
```

**Example: ALB Terraform**
```hcl
resource "aws_lb" "my_alb" {
  name               = "my-load-balancer"
  internal           = false
  load_balancer_type = "application"
  subnets            = ["subnet-xxx", "subnet-yyy"]
  
  tags = {
    Name = "my-alb"
    ManagedBy = "AWS-Cloud-Dashboard"
  }
}

resource "aws_lb_target_group" "my_tg" {
  name     = "my-target-group"
  port     = 80
  protocol = "HTTP"
  vpc_id   = "vpc-xxx"
  
  health_check {
    enabled             = true
    healthy_threshold   = 2
    interval            = 30
    matcher             = "200"
    path                = "/"
    port                = "traffic-port"
    protocol            = "HTTP"
    timeout             = 5
    unhealthy_threshold = 2
  }
}

resource "aws_lb_listener" "my_listener" {
  load_balancer_arn = aws_lb.my_alb.arn
  port              = "80"
  protocol          = "HTTP"
  
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.my_tg.arn
  }
}
```

---

## 📋 Pre-configured Templates

### Template 1: Web Server Stack
```hcl
# Complete web server with ALB, ASG, and RDS
module "web_server_stack" {
  source = "./modules/web-server"
  
  environment = "production"
  instance_type = "t3.small"
  min_size = 2
  max_size = 10
  desired_capacity = 2
}
```

### Template 2: Serverless API
```hcl
# DynamoDB + Lambda + API Gateway
module "serverless_api" {
  source = "./modules/serverless-api"
  
  table_name = "my-api-data"
  api_name = "my-api"
}
```

### Template 3: Static Website
```hcl
# S3 + CloudFront + ACM
module "static_website" {
  source = "./modules/static-website"
  
  domain_name = "example.com"
  bucket_name = "example-com-website"
}
```

---

## 🔧 Testing Connection

### Test 1: AWS CLI
```bash
# Test credentials
aws sts get-caller-identity

# Should return:
# {
#     "UserId": "AIDAXXXXXXXXXXXXXXXXX",
#     "Account": "123456789012",
#     "Arn": "arn:aws:iam::123456789012:user/dashboard-user"
# }
```

### Test 2: List Resources
```bash
# Test EC2 access
aws ec2 describe-instances --region us-east-1

# Test DynamoDB access
aws dynamodb list-tables --region us-east-1

# Test S3 access
aws s3 ls
```

### Test 3: Dashboard Health Check
```bash
curl http://localhost:5000/api/health

# Should return:
# {"status":"healthy","region":"us-east-1","timestamp":"..."}
```

---

## 🔒 Security Best Practices

### 1. Use IAM Roles When Possible
- Preferred for EC2 instances
- No credentials to manage
- Automatic rotation

### 2. Least Privilege Principle
- Only grant necessary permissions
- Use custom policies instead of *FullAccess
- Regularly review permissions

### 3. Rotate Access Keys
```bash
# Create new key
aws iam create-access-key --user-name dashboard-user

# Update configuration
aws configure

# Delete old key
aws iam delete-access-key --access-key-id OLD_KEY_ID --user-name dashboard-user
```

### 4. Enable MFA
- Add MFA to IAM user
- Require MFA for sensitive operations

### 5. Use AWS Secrets Manager
```python
import boto3
from botocore.exceptions import ClientError

def get_secret():
    secret_name = "dashboard/credentials"
    region_name = "us-east-1"
    
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )
    
    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
        return get_secret_value_response['SecretString']
    except ClientError as e:
        raise e
```

### 6. Monitor Access
- Enable CloudTrail
- Review CloudWatch logs
- Set up billing alerts

---

## 📊 Resource Discovery

### Automatic Resource Discovery Script

```python
import boto3
import json

def discover_resources(region='us-east-1'):
    """Discover all AWS resources in account"""
    
    resources = {
        'ec2_instances': [],
        'vpcs': [],
        'subnets': [],
        'security_groups': [],
        'key_pairs': [],
        'amis': [],
        'load_balancers': [],
        'dynamodb_tables': [],
        's3_buckets': [],
        'auto_scaling_groups': [],
        'certificates': []
    }
    
    # EC2 Resources
    ec2 = boto3.client('ec2', region_name=region)
    
    # Instances
    instances = ec2.describe_instances()
    for reservation in instances['Reservations']:
        for instance in reservation['Instances']:
            resources['ec2_instances'].append({
                'id': instance['InstanceId'],
                'type': instance['InstanceType'],
                'state': instance['State']['Name']
            })
    
    # VPCs
    vpcs = ec2.describe_vpcs()
    resources['vpcs'] = [{'id': vpc['VpcId'], 'cidr': vpc['CidrBlock']} 
                         for vpc in vpcs['Vpcs']]
    
    # Subnets
    subnets = ec2.describe_subnets()
    resources['subnets'] = [{'id': subnet['SubnetId'], 'vpc': subnet['VpcId']} 
                            for subnet in subnets['Subnets']]
    
    # Security Groups
    sgs = ec2.describe_security_groups()
    resources['security_groups'] = [{'id': sg['GroupId'], 'name': sg['GroupName']} 
                                    for sg in sgs['SecurityGroups']]
    
    # Key Pairs
    keys = ec2.describe_key_pairs()
    resources['key_pairs'] = [kp['KeyName'] for kp in keys['KeyPairs']]
    
    # Load Balancers
    elb = boto3.client('elbv2', region_name=region)
    lbs = elb.describe_load_balancers()
    resources['load_balancers'] = [{'name': lb['LoadBalancerName'], 
                                    'dns': lb['DNSName']} 
                                   for lb in lbs['LoadBalancers']]
    
    # DynamoDB Tables
    dynamodb = boto3.client('dynamodb', region_name=region)
    tables = dynamodb.list_tables()
    resources['dynamodb_tables'] = tables['TableNames']
    
    # S3 Buckets
    s3 = boto3.client('s3')
    buckets = s3.list_buckets()
    resources['s3_buckets'] = [b['Name'] for b in buckets['Buckets']]
    
    # Auto Scaling Groups
    asg = boto3.client('autoscaling', region_name=region)
    groups = asg.describe_auto_scaling_groups()
    resources['auto_scaling_groups'] = [g['AutoScalingGroupName'] 
                                        for g in groups['AutoScalingGroups']]
    
    # Certificates
    acm = boto3.client('acm', region_name=region)
    certs = acm.list_certificates()
    resources['certificates'] = [{'arn': c['CertificateArn'], 
                                  'domain': c['DomainName']} 
                                 for c in certs['CertificateSummaryList']]
    
    return resources

# Run discovery
if __name__ == '__main__':
    resources = discover_resources()
    print(json.dumps(resources, indent=2))
```

---

## ✅ Connection Checklist

Before using the dashboard:
- [ ] AWS credentials configured (IAM keys or role)
- [ ] Correct region selected
- [ ] IAM permissions granted
- [ ] AWS CLI installed and working
- [ ] Test connection: `aws sts get-caller-identity`
- [ ] Backend API can access AWS
- [ ] Health check returns "healthy"

Happy connecting! 🚀
