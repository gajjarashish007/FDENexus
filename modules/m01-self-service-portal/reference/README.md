# Reference: legacy self-service portal

Copy of the original `selfservice/` prototype (Flask + vanilla JS). Nothing in M01 imports it at runtime.
It is kept for features M01 does not have yet: static-website and code-upload deployments (`deploy_api.py`),
Terraform integration (`TERRAFORM-INTEGRATION.md`), DynamoDB, ALB, ASG and ACM forms (`backend-api.py`),
and the guides (`AWS-CONNECTION-GUIDE.md`, `REGION-GUIDE.md`, `TROUBLESHOOTING.md`).
Excluded on purpose: `ssp_data.db` (user data), `uploads/`, `__pycache__/`.
