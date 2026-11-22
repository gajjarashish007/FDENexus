# Creates a member account in AWS Organizations. Run against the management account.

variable "account_name" {
  type = string
}

variable "account_email" {
  type = string
}

variable "parent_id" {
  description = "Organizational unit id (ou-xxxx) or root id (r-xxxx)."
  type        = string
}

variable "close_on_deletion" {
  description = "Close the AWS account when this resource is destroyed. Otherwise it is only removed from state."
  type        = bool
  default     = false
}

resource "aws_organizations_account" "this" {
  name                       = var.account_name
  email                      = var.account_email
  parent_id                  = var.parent_id
  role_name                  = "OrganizationAccountAccessRole"
  iam_user_access_to_billing = "DENY"
  close_on_deletion          = var.close_on_deletion

  lifecycle {
    ignore_changes = [role_name, iam_user_access_to_billing]
  }
}
