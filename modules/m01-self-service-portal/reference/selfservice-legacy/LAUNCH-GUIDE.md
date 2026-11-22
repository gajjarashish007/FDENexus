# AWS Cloud Dashboard - Launch Guide

## 🚀 Quick Start

### Starting the Dashboard

1. **Start the Backend API:**
   ```bash
   python backend-api.py
   ```
   The API will start on `http://localhost:5000`

2. **Open the Dashboard:**
   - Open `index.html` in your browser
   - Or use the batch file: `start.bat`

### Dashboard Views

**Main Dashboard (`index.html`)**
- View all your AWS resources in card format
- Overview statistics at the top
- Organized by service type
- Create new resources from empty states

**Service Catalog (`dashboard.html`)**
- Browse all available AWS services
- See service descriptions and features
- Quick launch buttons for each service
- Metrics and pricing information

## 📋 Creating Resources

### EC2 Instance

The EC2 launch modal now features a beautiful card-based interface:

**Sections:**
1. **Instance Details** - Name your instance
2. **AMI Configuration** - Select your operating system
3. **Instance Type** - Choose from visual cards:
   - t2.micro (Free Tier) - 1 vCPU, 1 GB RAM
   - t2.small - 1 vCPU, 2 GB RAM
   - t2.medium - 2 vCPU, 4 GB RAM
   - t3.micro - 2 vCPU, 1 GB RAM
4. **Security** - Optional SSH key pair
5. **Cost Estimate** - See pricing before launch

**Features:**
- Visual instance type selection with cards
- Hover effects and animations
- Free Tier indicators
- Cost estimates
- Helpful descriptions for each field

### DynamoDB Table

Create NoSQL tables with:
- Table name
- Partition key (String/Number)
- Optional sort key
- Billing mode (On-Demand/Provisioned)

### Load Balancer (ALB/NLB)

Create load balancers with:
- Name and type (Application or Network)
- Subnets (minimum 2 in different AZs)
- Scheme (Internet-facing or Internal)
- Type-specific descriptions

### S3 Bucket

Create storage buckets with:
- Globally unique bucket name
- Optional static website hosting
- Automatic public access configuration for websites

### Auto Scaling Group

Create ASGs with:
- Name and launch template
- Min/Max/Desired capacity
- Subnets for distribution
- Health check configuration

### SSL Certificate

Request certificates with:
- Domain name (includes wildcard)
- Validation method (DNS or Email)
- Free and auto-renewing

## 🎨 UI Features

### Card-Based Layout

All resources are displayed as cards with:
- Resource name and ID
- Color-coded status badges
- Key metrics in grid layout
- Feature tags
- Hover animations

### Empty States

When no resources exist:
- Friendly icon and message
- "Create Your First [Resource]" button
- Encourages getting started

### Overview Statistics

Top bar shows totals for:
- EC2 Instances
- Load Balancers
- DynamoDB Tables
- S3 Buckets
- Auto Scaling Groups
- SSL Certificates

### Visual Feedback

- Loading states
- Success/error toast notifications
- Smooth animations
- Color-coded status indicators

## 🔧 Configuration

### AWS Credentials

Set up AWS credentials:
```bash
aws configure
```

Or set environment variables:
```bash
set AWS_ACCESS_KEY_ID=your_key
set AWS_SECRET_ACCESS_KEY=your_secret
set AWS_REGION=us-east-1
```

### Backend Configuration

Edit `backend-api.py` to change:
- AWS region
- Port number
- CORS settings

## 📊 Resource Status Colors

- **Green** - Running, Active, Issued
- **Red** - Stopped, Inactive, Failed
- **Yellow** - Pending, In Progress

## 🔄 Auto-Refresh

The dashboard automatically refreshes every 30 seconds to show the latest resource states.

## 💡 Tips

1. **Free Tier** - Use t2.micro instances to stay within free tier limits
2. **Naming** - Use descriptive names for easy identification
3. **Tags** - Resources show category tags for quick filtering
4. **Empty States** - Click "Create Your First" buttons for quick starts
5. **Service Catalog** - Browse all services before creating

## 🐛 Troubleshooting

**Connection Failed**
- Ensure backend API is running on port 5000
- Check AWS credentials are configured

**Resources Not Loading**
- Verify IAM permissions for the services
- Check AWS region is correct
- Look at browser console for errors

**Creation Fails**
- Check required fields are filled
- Verify AWS service limits
- Review error message in toast notification

## 📚 Next Steps

1. Launch your first EC2 instance
2. Create a DynamoDB table for data storage
3. Set up an S3 bucket for file storage
4. Request an SSL certificate for your domain
5. Configure a load balancer for high availability

Enjoy your AWS Cloud Dashboard! 🎉
