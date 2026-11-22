# AWS Cloud Dashboard

## 🚀 Quick Start

A beautiful, interactive dashboard for creating and managing AWS resources.

### Default Configuration
- **Region:** eu-west-1 (EU Ireland)
- **Backend:** http://localhost:5000
- **Services:** EC2, ALB, NLB, DynamoDB, S3, ASG, ACM, Static Websites

---

## 📦 Installation

### 1. Install Dependencies
```bash
pip install flask flask-cors boto3
```

### 2. Configure AWS Credentials
```bash
aws configure
# AWS Access Key ID: YOUR_KEY
# AWS Secret Access Key: YOUR_SECRET  
# Default region name: eu-west-1
# Default output format: json
```

### 3. Start Application
```bash
# Start backend
python backend-api.py

# Open dashboard
start index.html
```

---

## 🎯 Features

### Service Catalog
- 8 AWS services with beautiful cards
- One-click resource creation
- Deploy time and cost estimates
- Service descriptions and features

### My Resources
- Card-based resource display
- Real-time status updates
- Overview statistics
- Auto-refresh every 30 seconds

### Creation History
- Track all created resources
- Timestamps and details
- Persistent storage

### Troubleshooting
- Built-in diagnostics
- Common issues and solutions
- Health checks

---

## 🌍 Region Selection

**Default:** eu-west-1 (EU Ireland)

**Change Region:**
- Use dropdown in dashboard header
- Select from 16 AWS regions worldwide
- Resources reload automatically

**Available Regions:**
- Europe: eu-west-1, eu-west-2, eu-west-3, eu-central-1, eu-north-1
- North America: us-east-1, us-east-2, us-west-1, us-west-2, ca-central-1
- Asia Pacific: ap-south-1, ap-northeast-1, ap-northeast-2, ap-southeast-1, ap-southeast-2
- South America: sa-east-1

---

## 📋 Supported Services

| Service | Description | Deploy Time |
|---------|-------------|-------------|
| **EC2 Instance** 💻 | Virtual servers | 2 min |
| **Application Load Balancer** 🌐 | HTTP/HTTPS traffic distribution | 3 min |
| **Network Load Balancer** ⚡ | TCP/UDP ultra-low latency | 3 min |
| **DynamoDB Table** 📊 | NoSQL database | <1 min |
| **S3 Bucket** 🪣 | Object storage | 1 min |
| **Auto Scaling Group** 📈 | Auto-scale instances | 5 min |
| **SSL Certificate** 🔒 | Free SSL/TLS | 2 min |
| **Static Website** 🌐 | S3 website hosting | 1 min |

---

## 🎨 Dashboard Views

### 1. 🚀 Available Services (Default)
Browse and create AWS resources from beautiful service cards.

### 2. 📊 My Resources
View all your created resources with status and metrics.

### 3. 📜 History
Track creation history with timestamps.

### 4. 🔧 Troubleshoot
Built-in diagnostics and solutions.

---

## 🔐 Security

### IAM Permissions Required
```json
{
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Action": [
            "ec2:Describe*", "ec2:RunInstances",
            "elasticloadbalancing:Describe*", "elasticloadbalancing:Create*",
            "dynamodb:List*", "dynamodb:Describe*", "dynamodb:CreateTable",
            "s3:List*", "s3:CreateBucket", "s3:PutBucket*",
            "autoscaling:Describe*", "autoscaling:CreateAutoScalingGroup",
            "acm:List*", "acm:Describe*", "acm:RequestCertificate"
        ],
        "Resource": "*"
    }]
}
```

---

## 🔧 Troubleshooting

### Backend Not Starting
```bash
python --version  # Check Python 3.7+
pip install flask flask-cors boto3
python backend-api.py
```

### Connection Failed
```bash
curl http://localhost:5000/api/health
# Should return: {"status":"healthy","region":"eu-west-1"}
```

### AWS Credentials Issue
```bash
aws sts get-caller-identity
# Should return your account info
```

### Resources Not Loading
1. Check backend is running
2. Verify AWS credentials
3. Confirm correct region
4. Check IAM permissions
5. Look at browser console (F12)

---

## 📚 Documentation

- **README.md** - This file (quick start)
- **SETUP-SUMMARY.md** - Complete setup guide
- **AWS-CONNECTION-GUIDE.md** - AWS configuration
- **REGION-GUIDE.md** - Region selection
- **TROUBLESHOOTING.md** - Detailed troubleshooting
- **FINAL-README.md** - Full documentation

---

## ✅ Pre-Flight Checklist

- [ ] Python 3.7+ installed
- [ ] Dependencies installed (`pip install flask flask-cors boto3`)
- [ ] AWS credentials configured
- [ ] Backend API running
- [ ] Dashboard opens in browser
- [ ] Connection status shows "Connected"

---

## 🎉 You're Ready!

Your AWS Cloud Dashboard is configured with:
- ✅ Default region: eu-west-1
- ✅ 8 AWS services
- ✅ Beautiful responsive UI
- ✅ Region selector
- ✅ Creation history
- ✅ Built-in troubleshooting

**Start creating AWS resources!** 🚀

---

## 💡 Quick Tips

1. Start with EC2 t2.micro (Free Tier)
2. Use descriptive resource names
3. Check costs before creating
4. Use region dropdown to switch regions
5. Press F12 for browser console
6. Check backend terminal for errors
7. Run diagnostics in Troubleshoot tab

---

## 📞 Support

**Common Issues:**
- Backend not running → `python backend-api.py`
- Connection failed → Check port 5000
- AWS errors → Verify credentials and permissions
- Modal not opening → Clear browser cache

**Health Check:**
```bash
curl http://localhost:5000/api/health
```

---

Made with ❤️ for AWS Cloud Management

**Default Region:** 🌍 eu-west-1 (EU Ireland)
