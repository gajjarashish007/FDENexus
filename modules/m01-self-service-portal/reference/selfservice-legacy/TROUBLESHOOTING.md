# AWS Cloud Dashboard - Troubleshooting Guide

## 🔧 Common Issues and Solutions

### Issue: "Error launching instance" when creating EC2

**Possible Causes:**
1. Backend API not running
2. AWS credentials not configured
3. Invalid AMI ID
4. Insufficient IAM permissions
5. Instance type not selected properly

**Solutions:**

**1. Check Backend API**
```bash
# Ensure backend is running
python backend-api.py

# You should see:
# Starting AWS Cloud Dashboard API on http://localhost:5000
```

**2. Verify AWS Credentials**
```bash
# Check if credentials are configured
aws configure list

# If not configured, run:
aws configure
# Enter your AWS Access Key ID
# Enter your AWS Secret Access Key
# Enter default region (e.g., us-east-1)
```

**3. Test AWS Connection**
```bash
# Test if you can list EC2 instances
aws ec2 describe-instances --region us-east-1

# If this fails, your credentials are incorrect
```

**4. Check IAM Permissions**
Your AWS user/role needs these permissions:
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ec2:DescribeInstances",
                "ec2:RunInstances",
                "ec2:DescribeImages",
                "ec2:DescribeKeyPairs"
            ],
            "Resource": "*"
        }
    ]
}
```

**5. Verify AMI ID**
- Default AMI: `ami-0c55b159cbfafe1f0`
- Check if AMI exists in your region:
```bash
aws ec2 describe-images --image-ids ami-0c55b159cbfafe1f0 --region us-east-1
```

**6. Check Browser Console**
- Open browser Developer Tools (F12)
- Go to Console tab
- Look for error messages
- Common errors:
  - `Failed to fetch` - Backend not running
  - `CORS error` - Backend CORS not configured
  - `401/403` - AWS credentials issue

**7. Check Backend Logs**
Look at the terminal where backend is running for error messages:
```
Error: Unable to locate credentials
Error: The security token included in the request is invalid
Error: An error occurred (InvalidAMIID.NotFound)
```

---

### Issue: Modal doesn't open when clicking create buttons

**Solutions:**

**1. Check JavaScript Files**
- Ensure all JS files are loaded
- Open browser console (F12)
- Look for 404 errors for JS files

**2. Clear Browser Cache**
```
Ctrl + Shift + Delete (Windows)
Cmd + Shift + Delete (Mac)
```

**3. Check File Paths**
Ensure these files exist:
- `app.js`
- `app-extended.js`
- `resources-cards.js`

**4. Verify Modal HTML**
Check if modal element exists in HTML:
```html
<div id="modal" class="modal">
```

---

### Issue: Submit button doesn't work

**Solutions:**

**1. Wait for Modal to Load**
- Modal needs 100ms to initialize
- Wait for instance type cards to appear

**2. Select Instance Type**
- For EC2, you MUST click an instance type card
- Card should have blue border when selected

**3. Fill Required Fields**
- Instance name (optional but recommended)
- AMI ID (required)
- Instance type (required - click card)

**4. Check Event Handler**
- Submit button should have onclick handler
- Check browser console for errors

---

### Issue: Resources not loading

**Solutions:**

**1. Check Backend Connection**
```bash
# Test health endpoint
curl http://localhost:5000/api/health

# Should return:
# {"status":"healthy","region":"us-east-1"}
```

**2. Check AWS Region**
- Ensure resources exist in the configured region
- Default region: us-east-1
- Change region in backend-api.py if needed

**3. Verify IAM Permissions**
Need read permissions for all services:
```
ec2:DescribeInstances
elasticloadbalancing:DescribeLoadBalancers
dynamodb:ListTables
dynamodb:DescribeTable
s3:ListAllMyBuckets
autoscaling:DescribeAutoScalingGroups
acm:ListCertificates
acm:DescribeCertificate
```

**4. Check Network**
- Ensure internet connection
- Check firewall settings
- Verify no proxy blocking requests

---

### Issue: CORS errors in browser console

**Solution:**

**1. Verify Flask-CORS**
```bash
pip install flask-cors
```

**2. Check backend-api.py**
```python
from flask_cors import CORS
app = Flask(__name__)
CORS(app)  # This line must be present
```

**3. Restart Backend**
```bash
# Stop backend (Ctrl+C)
# Start again
python backend-api.py
```

---

### Issue: "Connection Failed" status

**Solutions:**

**1. Backend Not Running**
```bash
# Start backend
python backend-api.py
```

**2. Wrong Port**
- Backend runs on port 5000
- Check if another app is using port 5000
- Change port in backend-api.py if needed

**3. Firewall Blocking**
- Allow Python through firewall
- Allow port 5000

---

### Issue: Instance type card not selecting

**Solutions:**

**1. Wait for Modal Load**
- Cards initialize after 100ms
- Wait for modal to fully render

**2. Click Directly on Card**
- Click anywhere on the card area
- Card should get blue border

**3. Check JavaScript**
- Open console (F12)
- Look for errors in selectInstanceType function

**4. Manual Selection**
```javascript
// In console, try:
document.getElementById('instance-type').value = 't2.micro';
```

---

### Issue: Toast notifications not showing

**Solutions:**

**1. Check Toast Element**
```html
<div id="toast" class="toast"></div>
```

**2. Check CSS**
- Toast should have z-index: 2000
- Position: fixed
- Bottom: 30px, Right: 30px

**3. Check showToast Function**
```javascript
function showToast(message, type) {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.style.display = 'block';
    // ... rest of function
}
```

---

### Issue: AWS credentials not working

**Solutions:**

**1. Reconfigure Credentials**
```bash
aws configure
```

**2. Use Environment Variables**
```bash
# Windows
set AWS_ACCESS_KEY_ID=your_key
set AWS_SECRET_ACCESS_KEY=your_secret
set AWS_REGION=us-east-1

# Linux/Mac
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
export AWS_REGION=us-east-1
```

**3. Use IAM Role (EC2)**
If running on EC2, attach IAM role with required permissions

**4. Check Credentials File**
```bash
# Windows
type %USERPROFILE%\.aws\credentials

# Linux/Mac
cat ~/.aws/credentials
```

---

### Issue: Resources created but not showing

**Solutions:**

**1. Switch to Resources View**
- Click "📊 My Resources" tab
- Resources should appear

**2. Manual Refresh**
- Click refresh button (↻) for each section
- Or wait 30 seconds for auto-refresh

**3. Check Correct Region**
- Resources must be in same region as backend
- Default: us-east-1

**4. Verify Resource Created**
```bash
# Check in AWS Console
# Or use AWS CLI
aws ec2 describe-instances
aws dynamodb list-tables
aws s3 ls
```

---

## 🔍 Debugging Steps

### Step 1: Check Backend
```bash
# Terminal 1
python backend-api.py

# Should show:
# Starting AWS Cloud Dashboard API on http://localhost:5000
# * Running on http://0.0.0.0:5000
```

### Step 2: Test API
```bash
# Terminal 2
curl http://localhost:5000/api/health

# Should return:
# {"status":"healthy","region":"us-east-1","timestamp":"..."}
```

### Step 3: Check Browser Console
1. Open browser (Chrome/Firefox/Edge)
2. Press F12
3. Go to Console tab
4. Look for errors (red text)
5. Look for network errors

### Step 4: Check Network Tab
1. F12 → Network tab
2. Click create button
3. Look for API calls
4. Check response status (should be 200 or 201)
5. Check response body for errors

### Step 5: Check Backend Logs
Look at terminal where backend is running:
- Request logs
- Error messages
- Stack traces

---

## 📋 Quick Checklist

Before creating resources:
- [ ] Backend API is running
- [ ] AWS credentials configured
- [ ] Correct region selected
- [ ] IAM permissions granted
- [ ] Browser console shows no errors
- [ ] Health check returns "healthy"

When creating EC2:
- [ ] Instance name entered (optional)
- [ ] AMI ID is valid
- [ ] Instance type card clicked (blue border)
- [ ] Key pair name (optional)
- [ ] Submit button clicked

---

## 🆘 Still Having Issues?

### Collect Debug Information

**1. Backend Logs**
```bash
python backend-api.py > backend.log 2>&1
```

**2. Browser Console**
- F12 → Console
- Copy all error messages

**3. Network Requests**
- F12 → Network
- Find failed request
- Copy request/response

**4. AWS CLI Test**
```bash
aws ec2 describe-instances --region us-east-1
aws sts get-caller-identity
```

**5. System Information**
- Operating System
- Python version: `python --version`
- Boto3 version: `pip show boto3`
- Flask version: `pip show flask`

---

## 💡 Pro Tips

1. **Always check backend logs first**
2. **Use browser console for frontend issues**
3. **Test AWS CLI before using dashboard**
4. **Start with simple resources (EC2)**
5. **Use Free Tier eligible options**
6. **Keep backend terminal visible**
7. **Refresh page if things look broken**
8. **Clear cache if CSS looks wrong**

---

## 📞 Common Error Messages

### "Failed to fetch"
- Backend not running
- Wrong URL/port
- CORS issue

### "Error launching instance"
- AWS credentials issue
- IAM permissions missing
- Invalid AMI ID
- Network error

### "Please fill required fields"
- Instance type not selected
- AMI ID missing
- Form validation failed

### "Connection Failed"
- Backend not accessible
- Port 5000 blocked
- Firewall issue

### "401 Unauthorized"
- AWS credentials invalid
- Credentials expired
- Wrong access key

### "403 Forbidden"
- IAM permissions insufficient
- Resource policy blocking
- Service control policy

---

## ✅ Success Indicators

You know it's working when:
- ✅ Backend shows "Running on http://0.0.0.0:5000"
- ✅ Status badge shows "Connected"
- ✅ Health check returns healthy
- ✅ Modal opens when clicking create
- ✅ Instance type card gets blue border
- ✅ Submit shows success toast
- ✅ Resource appears in My Resources view

Happy troubleshooting! 🔧
