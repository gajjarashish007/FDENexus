# AWS Region Selection Guide

## 🌍 Available Regions

The dashboard supports all major AWS regions worldwide.

### Default Region
**EU (Ireland) - eu-west-1**

This is the default region for the dashboard. You can change it anytime using the region selector.

---

## 📍 Region List

### North America
- **us-east-1** - US East (N. Virginia)
- **us-east-2** - US East (Ohio)
- **us-west-1** - US West (N. California)
- **us-west-2** - US West (Oregon)
- **ca-central-1** - Canada (Central)

### Europe
- **eu-west-1** - EU (Ireland) ⭐ Default
- **eu-west-2** - EU (London)
- **eu-west-3** - EU (Paris)
- **eu-central-1** - EU (Frankfurt)
- **eu-north-1** - EU (Stockholm)

### Asia Pacific
- **ap-south-1** - Asia Pacific (Mumbai)
- **ap-northeast-1** - Asia Pacific (Tokyo)
- **ap-northeast-2** - Asia Pacific (Seoul)
- **ap-southeast-1** - Asia Pacific (Singapore)
- **ap-southeast-2** - Asia Pacific (Sydney)

### South America
- **sa-east-1** - South America (São Paulo)

---

## 🔄 How to Change Region

### Method 1: Dashboard UI (Recommended)
1. Open the dashboard
2. Look at the top header
3. Find the "🌍 Region:" dropdown
4. Select your desired region
5. Resources will reload automatically

### Method 2: Backend Configuration
Edit `backend-api.py`:
```python
AWS_REGION = os.environ.get('AWS_REGION', 'eu-west-1')
```

### Method 3: Environment Variable
```bash
# Windows
set AWS_REGION=eu-west-1
python backend-api.py

# Linux/Mac
export AWS_REGION=eu-west-1
python backend-api.py
```

### Method 4: AWS CLI Configuration
```bash
aws configure set region eu-west-1
```

---

## 🎯 Region Selection Tips

### Choose Based On:

**1. Latency**
- Select region closest to your users
- Lower latency = better performance

**2. Compliance**
- GDPR: Use EU regions
- Data residency requirements
- Industry regulations

**3. Service Availability**
- Not all services available in all regions
- Check AWS Regional Services list

**4. Cost**
- Pricing varies by region
- EU regions typically more expensive than US
- Check AWS pricing calculator

**5. Disaster Recovery**
- Use multiple regions for redundancy
- Cross-region replication

---

## 📊 Region Comparison

| Region | Latency (EU) | Services | Cost | Best For |
|--------|-------------|----------|------|----------|
| eu-west-1 | Lowest | All | Medium | EU users, GDPR |
| eu-central-1 | Low | All | Medium | Central EU, Germany |
| us-east-1 | High | Most | Lowest | US users, testing |
| ap-southeast-1 | Very High | Most | Medium | Asia Pacific |

---

## 🔍 Check Current Region

### Dashboard
Look at the region dropdown in the header.

### AWS CLI
```bash
aws configure get region
```

### Backend API
```bash
curl http://localhost:5000/api/region
```

---

## ⚠️ Important Notes

### 1. Resources are Region-Specific
- EC2 instances in eu-west-1 won't show in us-east-1
- Each region is independent
- Must create resources in each region separately

### 2. S3 Buckets are Global
- Bucket names must be globally unique
- But buckets are created in specific regions
- Access from any region (with latency)

### 3. IAM is Global
- IAM users, roles, policies are global
- Work across all regions
- No need to recreate per region

### 4. Some Services are Global
- CloudFront (CDN)
- Route 53 (DNS)
- IAM
- WAF

### 5. Cross-Region Costs
- Data transfer between regions costs money
- Keep resources in same region when possible

---

## 🚀 Multi-Region Strategy

### Development
```
Single region: eu-west-1
- All resources in one region
- Simplest setup
- Lowest cost
```

### Production
```
Primary: eu-west-1
Secondary: eu-central-1
- High availability
- Disaster recovery
- Load distribution
```

### Global
```
EU: eu-west-1
US: us-east-1
Asia: ap-southeast-1
- Lowest latency worldwide
- Regional compliance
- Highest cost
```

---

## 🔧 Troubleshooting

### Issue: Resources not showing after region change

**Solution:**
1. Wait a few seconds for reload
2. Click refresh button
3. Check if resources exist in that region
4. Verify IAM permissions for the region

### Issue: "Region not supported" error

**Solution:**
1. Check if service is available in that region
2. Verify AWS account has access to region
3. Some new regions require opt-in

### Issue: Different resources in different regions

**Solution:**
This is normal! Resources are region-specific.
- Create resources in each region you need
- Or use infrastructure as code (Terraform) to deploy to multiple regions

---

## 📋 Region Checklist

Before changing region:
- [ ] Check service availability
- [ ] Verify IAM permissions
- [ ] Consider latency impact
- [ ] Review pricing differences
- [ ] Plan for data transfer costs
- [ ] Ensure compliance requirements met

---

## 💡 Best Practices

### 1. Start with One Region
- Master one region first
- Expand to others as needed

### 2. Use Closest Region
- Better performance
- Lower latency
- Happier users

### 3. Consider Compliance
- GDPR: EU regions
- Data sovereignty laws
- Industry regulations

### 4. Plan for Growth
- Start small
- Add regions as you scale
- Use multi-region for HA

### 5. Monitor Costs
- Different regions = different costs
- Data transfer adds up
- Use Cost Explorer

---

## 🌐 Region Endpoints

Each region has its own endpoint:

```
eu-west-1: ec2.eu-west-1.amazonaws.com
us-east-1: ec2.us-east-1.amazonaws.com
ap-southeast-1: ec2.ap-southeast-1.amazonaws.com
```

The dashboard handles this automatically!

---

## ✅ Quick Reference

**Default Region:** eu-west-1 (EU Ireland)

**Change Region:** Use dropdown in dashboard header

**Check Region:** Look at header or run:
```bash
curl http://localhost:5000/api/region
```

**Resources:** Region-specific (except S3 bucket names, IAM)

**Cost:** Varies by region

**Latency:** Choose closest region

Happy region hopping! 🌍
