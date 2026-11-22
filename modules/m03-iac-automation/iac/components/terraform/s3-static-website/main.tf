variable "bucket_name" {
  type = string
}

variable "hosting" {
  description = "cloudfront: private bucket behind CloudFront (HTTPS). s3-website: public S3 website endpoint (HTTP only)."
  type        = string
  default     = "cloudfront"
  validation {
    condition     = contains(["cloudfront", "s3-website"], var.hosting)
    error_message = "hosting must be cloudfront or s3-website."
  }
}

variable "index_document" {
  type    = string
  default = "index.html"
}

variable "error_document" {
  type    = string
  default = "error.html"
}

variable "price_class" {
  type    = string
  default = "PriceClass_100"
}

locals {
  use_cf = var.hosting == "cloudfront"
}

resource "aws_s3_bucket" "site" {
  bucket = var.bucket_name
  tags   = { Name = var.bucket_name }
}

resource "aws_s3_bucket_ownership_controls" "site" {
  bucket = aws_s3_bucket.site.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "site" {
  bucket = aws_s3_bucket.site.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "site" {
  bucket = aws_s3_bucket.site.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# CloudFront mode keeps the bucket private. Website mode allows a public-read policy on purpose.
resource "aws_s3_bucket_public_access_block" "site" {
  bucket                  = aws_s3_bucket.site.id
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = local.use_cf
  restrict_public_buckets = local.use_cf
}

resource "aws_s3_bucket_website_configuration" "site" {
  count  = local.use_cf ? 0 : 1
  bucket = aws_s3_bucket.site.id
  index_document {
    suffix = var.index_document
  }
  error_document {
    key = var.error_document
  }
}

resource "aws_cloudfront_origin_access_control" "site" {
  count                             = local.use_cf ? 1 : 0
  name                              = substr("oac-${var.bucket_name}", 0, 64)
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_response_headers_policy" "site" {
  count = local.use_cf ? 1 : 0
  name  = substr("fde-${var.environment_id}-${replace(var.bucket_name, ".", "-")}", 0, 128)
  security_headers_config {
    strict_transport_security {
      access_control_max_age_sec = 31536000
      include_subdomains         = true
      override                   = true
    }
    content_type_options {
      override = true
    }
    frame_options {
      frame_option = "DENY"
      override     = true
    }
    referrer_policy {
      referrer_policy = "strict-origin-when-cross-origin"
      override        = true
    }
  }
}

resource "aws_cloudfront_distribution" "site" {
  count               = local.use_cf ? 1 : 0
  enabled             = true
  default_root_object = var.index_document
  price_class         = var.price_class
  comment             = "FDE Nexus ${var.environment_id} ${var.bucket_name}"
  http_version        = "http2and3"

  origin {
    domain_name              = aws_s3_bucket.site.bucket_regional_domain_name
    origin_id                = "s3-site"
    origin_access_control_id = aws_cloudfront_origin_access_control.site[0].id
  }

  default_cache_behavior {
    target_origin_id           = "s3-site"
    viewer_protocol_policy     = "redirect-to-https"
    allowed_methods            = ["GET", "HEAD"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = "658327ea-f89d-4fab-a63d-7e88639e58f6" # Managed-CachingOptimized
    response_headers_policy_id = aws_cloudfront_response_headers_policy.site[0].id
  }

  custom_error_response {
    error_code         = 403
    response_code      = 404
    response_page_path = "/${var.error_document}"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
    minimum_protocol_version       = "TLSv1.2_2021"
  }
}

data "aws_iam_policy_document" "site" {
  dynamic "statement" {
    for_each = local.use_cf ? [1] : []
    content {
      sid       = "AllowCloudFrontRead"
      actions   = ["s3:GetObject"]
      resources = ["${aws_s3_bucket.site.arn}/*"]
      principals {
        type        = "Service"
        identifiers = ["cloudfront.amazonaws.com"]
      }
      condition {
        test     = "StringEquals"
        variable = "AWS:SourceArn"
        values   = [aws_cloudfront_distribution.site[0].arn]
      }
    }
  }

  dynamic "statement" {
    for_each = local.use_cf ? [] : [1]
    content {
      sid       = "PublicRead"
      actions   = ["s3:GetObject"]
      resources = ["${aws_s3_bucket.site.arn}/*"]
      principals {
        type        = "*"
        identifiers = ["*"]
      }
    }
  }
}

resource "aws_s3_bucket_policy" "site" {
  bucket     = aws_s3_bucket.site.id
  policy     = data.aws_iam_policy_document.site.json
  depends_on = [aws_s3_bucket_public_access_block.site]
}
