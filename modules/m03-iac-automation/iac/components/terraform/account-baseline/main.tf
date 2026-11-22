# Per account + region security baseline.
# Account-wide settings (S3 public access block, IAM password policy) are managed once per
# account: the portal sets manage_account_wide = true only on the first baseline in an account.

variable "manage_account_wide" {
  type    = bool
  default = true
}

variable "enable_guardduty" {
  description = "Leave false when GuardDuty is managed centrally by AWS Organizations."
  type        = bool
  default     = false
}

variable "enable_access_analyzer" {
  type    = bool
  default = true
}

resource "aws_ebs_encryption_by_default" "this" {
  enabled = true
}

resource "aws_s3_account_public_access_block" "this" {
  count                   = var.manage_account_wide ? 1 : 0
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_iam_account_password_policy" "this" {
  count                          = var.manage_account_wide ? 1 : 0
  minimum_password_length        = 14
  require_lowercase_characters   = true
  require_uppercase_characters   = true
  require_numbers                = true
  require_symbols                = true
  allow_users_to_change_password = true
  password_reuse_prevention      = 24
  max_password_age               = 90
}

resource "aws_accessanalyzer_analyzer" "this" {
  count         = var.enable_access_analyzer ? 1 : 0
  analyzer_name = "fde-nexus-${var.region}"
  type          = "ACCOUNT"
}

resource "aws_guardduty_detector" "this" {
  count  = var.enable_guardduty ? 1 : 0
  enable = true
}
