# Terraform Integration Guide

## 🏗️ Overview

All AWS resources are now created using Terraform for:
- Infrastructure as Code (IaC)
- Version control
- Reproducibility
- Easy cleanup
- State management

---

## 📋 Features

### 1. Terraform Resource Creation
- All services created via Terraform
- Automatic .tf file generation
- State file management
- Output display

### 2. View Terraform Code
- See generated Terraform code
- Download .tf files
- Copy to clipboard
- Syntax highlighting

### 3. Resource Deletion
- Terraform destroy
- Clean state removal
- Confirmation dialogs
- Rollback support

### 4. History Tracking
- Creation timestamps
- Terraform outputs
- Resource metadata
- Deletion records

---

## 🚀 How It Works

### Resource Creation Flow

```
User clicks "Create" 
    ↓
Dashboard generates Terraform code
    ↓
Backend runs: terraform init
    ↓
Backend runs: terraform plan
    ↓
Backend runs: terraform apply
    ↓
Terraform output displayed
    ↓
Resource added to history
```

### Resource Deletion Flow

```
User clicks "Delete"
    ↓
Confirmation dialog
    ↓
Backend runs: terraform destroy
    ↓
State file removed
    ↓
History updated
    ↓
Resource removed from view
```

---

## 📁 File Structure

```
selfservice/
├── terraform/
│   ├── ec2/
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   ├── outputs.tf
│   │   └── terraform.tfstate
│   ├── dynamodb/
│   ├── s3/
│   ├── alb/
│   ├── asg/
│   └── acm/
├── backend-api.py
└── index.html
```

---

## 🔧 Backend API Endpoints

### Terraform Operations

```python
# Create resource with Terraform
POST /api/terraform/create
{
    "service": "ec2",
    "config": {...}
}

# Get Terraform output
GET /api/terraform/output/{resource_id}

# View Terraform code
GET /api/terraform/code/{resource_id}

# Destroy resource
DELETE /api/terraform/destroy/{resource_id}

# List all Terraform states
GET /api/terraform/states
```

---

## 📊 Terraform Templates

### EC2 Instance

```hcl
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

resource "aws_instance" "main" {
  ami           = var.ami_id
  instance_type = var.instance_type
  
  tags = {
    Name      = var.instance_name
    ManagedBy = "AWS-Cloud-Dashboard"
    CreatedAt = timestamp()
  }
}

output "instance_id" {
  value = aws_instance.main.id
}

output "public_ip" {
  value = aws_instance.main.public_ip
}

output "private_ip" {
  value = aws_instance.main.private_ip
}
```

### DynamoDB Table

```hcl
resource "aws_dynamodb_table" "main" {
  name           = var.table_name
  billing_mode   = var.billing_mode
  hash_key       = var.partition_key
  
  attribute {
    name = var.partition_key
    type = var.partition_key_type
  }
  
  tags = {
    Name      = var.table_name
    ManagedBy = "AWS-Cloud-Dashboard"
  }
}

output "table_name" {
  value = aws_dynamodb_table.main.name
}

output "table_arn" {
  value = aws_dynamodb_table.main.arn
}
```

### S3 Bucket

```hcl
resource "aws_s3_bucket" "main" {
  bucket = var.bucket_name
  
  tags = {
    Name      = var.bucket_name
    ManagedBy = "AWS-Cloud-Dashboard"
  }
}

resource "aws_s3_bucket_website_configuration" "main" {
  count  = var.enable_website ? 1 : 0
  bucket = aws_s3_bucket.main.id
  
  index_document {
    suffix = "index.html"
  }
}

output "bucket_name" {
  value = aws_s3_bucket.main.id
}

output "bucket_arn" {
  value = aws_s3_bucket.main.arn
}

output "website_endpoint" {
  value = var.enable_website ? aws_s3_bucket_website_configuration.main[0].website_endpoint : ""
}
```

---

## 🎨 UI Features

### Resource Card with Actions

```
┌──────────────────────────────────────┐
│  💻 my-web-server      [RUNNING]     │
│  i-1234567890abcdef0                 │
│                                      │
│  Type: t2.micro                      │
│  Public IP: 54.123.45.67             │
│                                      │
│  [View Code] [View Output] [Delete]  │
└──────────────────────────────────────┘
```

### Terraform Output Modal

```
┌──────────────────────────────────────┐
│  Terraform Output                    │
│  ────────────────────────────────    │
│                                      │
│  instance_id = "i-1234567890abcdef0" │
│  public_ip   = "54.123.45.67"        │
│  private_ip  = "10.0.1.23"           │
│                                      │
│  [Copy] [Download] [Close]           │
└──────────────────────────────────────┘
```

### Terraform Code Modal

```
┌──────────────────────────────────────┐
│  Terraform Code                      │
│  ────────────────────────────────    │
│                                      │
│  resource "aws_instance" "main" {    │
│    ami           = "ami-xxx"         │
│    instance_type = "t2.micro"        │
│  }                                   │
│                                      │
│  [Copy] [Download] [Close]           │
└──────────────────────────────────────┘
```

---

## 📜 History Features

### History View

```
┌──────────────────────────────────────┐
│  📜 Creation History                 │
│  ────────────────────────────────    │
│                                      │
│  💻 my-web-server                    │
│  Created: 2024-01-15 10:30:45        │
│  Type: EC2 Instance                  │
│  Status: Active                      │
│  [View Details] [View Code]          │
│                                      │
│  📊 my-table                         │
│  Created: 2024-01-15 09:15:22        │
│  Type: DynamoDB Table                │
│  Status: Active                      │
│  [View Details] [View Code]          │
│                                      │
│  🪣 my-bucket (DELETED)              │
│  Created: 2024-01-14 14:20:10        │
│  Deleted: 2024-01-15 11:45:30        │
│  Type: S3 Bucket                     │
│  [View Details]                      │
└──────────────────────────────────────┘
```

### History Entry Details

```json
{
  "id": "res-1234567890",
  "type": "EC2",
  "name": "my-web-server",
  "created_at": "2024-01-15T10:30:45Z",
  "deleted_at": null,
  "status": "active",
  "terraform_code": "...",
  "terraform_output": {
    "instance_id": "i-1234567890abcdef0",
    "public_ip": "54.123.45.67"
  },
  "config": {
    "ami_id": "ami-xxx",
    "instance_type": "t2.micro"
  }
}
```

---

## 🗑️ Delete Functionality

### Confirmation Dialog

```
┌──────────────────────────────────────┐
│  ⚠️ Confirm Deletion                 │
│  ────────────────────────────────    │
│                                      │
│  Are you sure you want to delete:    │
│                                      │
│  Resource: my-web-server             │
│  Type: EC2 Instance                  │
│  ID: i-1234567890abcdef0             │
│                                      │
│  This will run:                      │
│  terraform destroy                   │
│                                      │
│  ⚠️ This action cannot be undone!    │
│                                      │
│  [Cancel] [Delete]                   │
└──────────────────────────────────────┘
```

### Deletion Process

1. User clicks "Delete" button
2. Confirmation modal appears
3. User confirms deletion
4. Backend runs `terraform destroy`
5. State file removed
6. History updated with deletion timestamp
7. Resource removed from active view
8. Success toast notification

---

## 💾 State Management

### Terraform State Files

```
terraform/
├── ec2/
│   ├── my-web-server/
│   │   ├── main.tf
│   │   ├── terraform.tfstate
│   │   └── terraform.tfstate.backup
│   └── another-instance/
│       └── ...
├── dynamodb/
│   └── my-table/
│       └── ...
└── s3/
    └── my-bucket/
        └── ...
```

### State Backup

- Automatic backup before destroy
- State history maintained
- Rollback capability
- Export/import support

---

## 🔄 Workflow Examples

### Create EC2 Instance

```bash
# User fills form in dashboard
# Backend generates:

# 1. Create directory
mkdir -p terraform/ec2/my-web-server

# 2. Generate main.tf
cat > terraform/ec2/my-web-server/main.tf << EOF
resource "aws_instance" "main" {
  ami           = "ami-xxx"
  instance_type = "t2.micro"
  tags = {
    Name = "my-web-server"
  }
}
EOF

# 3. Initialize
cd terraform/ec2/my-web-server
terraform init

# 4. Apply
terraform apply -auto-approve

# 5. Get output
terraform output -json

# 6. Store in history
```

### Delete Resource

```bash
# User clicks delete
# Backend executes:

# 1. Navigate to resource directory
cd terraform/ec2/my-web-server

# 2. Backup state
cp terraform.tfstate terraform.tfstate.backup

# 3. Destroy
terraform destroy -auto-approve

# 4. Update history
# Mark as deleted with timestamp

# 5. Archive files
mv terraform/ec2/my-web-server terraform/archived/
```

---

## 📊 Benefits

### Infrastructure as Code
- ✅ Version controlled
- ✅ Reproducible
- ✅ Documented
- ✅ Auditable

### Easy Management
- ✅ One-click creation
- ✅ One-click deletion
- ✅ View code anytime
- ✅ Export configurations

### History Tracking
- ✅ Complete audit trail
- ✅ Creation timestamps
- ✅ Deletion records
- ✅ Configuration history

### Safety
- ✅ Confirmation dialogs
- ✅ State backups
- ✅ Rollback support
- ✅ Error handling

---

## 🚀 Getting Started

### Prerequisites

```bash
# Install Terraform
# Windows: choco install terraform
# Mac: brew install terraform
# Linux: apt-get install terraform

# Verify installation
terraform version
```

### Configuration

```python
# backend-api.py
TERRAFORM_DIR = './terraform'
TERRAFORM_BIN = 'terraform'  # or full path

# Enable Terraform mode
USE_TERRAFORM = True
```

### Usage

1. **Create Resource**
   - Click "Create" button
   - Fill in form
   - Submit
   - View Terraform output

2. **View Code**
   - Click "View Code" on resource card
   - See generated Terraform
   - Copy or download

3. **Delete Resource**
   - Click "Delete" button
   - Confirm deletion
   - Resource destroyed via Terraform

4. **View History**
   - Click "History" tab
   - See all created/deleted resources
   - View details and code

---

## 📝 Notes

- All resources tagged with `ManagedBy = "AWS-Cloud-Dashboard"`
- State files stored locally
- Automatic cleanup on deletion
- History persisted in database
- Terraform output displayed in UI

---

## 🎯 Next Steps

1. Install Terraform
2. Configure backend
3. Test resource creation
4. Verify Terraform output
5. Test deletion
6. Check history

Your dashboard now uses Terraform for all AWS resource management! 🎉
