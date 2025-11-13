resource "random_id" "web_bucket_suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "web_ui" {
  bucket        = local.web_bucket_name
  force_destroy = true
  tags          = local.tags
}

resource "aws_cloudfront_function" "admin_basic_auth" {
  name    = "${var.project_name}-admin-basic-auth"
  runtime = "cloudfront-js-1.0"
  publish = true
  code    = templatefile("${path.module}/../cloudfront/admin_basic_auth.js", {
    basic_header = local.admin_basic_auth_header
  })
}

resource "aws_s3_bucket_ownership_controls" "web_ui" {
  bucket = aws_s3_bucket.web_ui.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "web_ui" {
  bucket = aws_s3_bucket.web_ui.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "web_ui" {
  bucket = aws_s3_bucket.web_ui.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_object" "web_ui_files" {
  for_each = {
    "index.html" = {
      source = "${path.module}/../web/index.html"
      content_type = "text/html"
    }
    "admin.html" = {
      source = "${path.module}/../web/admin.html"
      content_type = "text/html"
    }
    "unavailable.html" = {
      source = "${path.module}/../web/unavailable.html"
      content_type = "text/html"
    }
    "styles.css" = {
      source = "${path.module}/../web/styles.css"
      content_type = "text/css"
    }
  }

  bucket       = aws_s3_bucket.web_ui.id
  key          = each.key
  source       = each.value.source
  content_type = each.value.content_type
  etag         = filemd5(each.value.source)
  cache_control = "no-cache"

  depends_on = [
    aws_s3_bucket_ownership_controls.web_ui,
    aws_s3_bucket_public_access_block.web_ui
  ]
}

resource "aws_cloudfront_origin_access_control" "web_ui" {
  name                              = "${var.project_name}-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_distribution" "web_ui" {
  enabled             = true
  is_ipv6_enabled     = true
  comment             = "Distribution for VPN control Web UI"
  default_root_object = "index.html"

  origin {
    domain_name = aws_s3_bucket.web_ui.bucket_regional_domain_name
    origin_id   = "s3-web-ui"

    origin_access_control_id = aws_cloudfront_origin_access_control.web_ui.id

    s3_origin_config {
      origin_access_identity = ""
    }
  }

  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "s3-web-ui"

    viewer_protocol_policy = "redirect-to-https"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    min_ttl                = 0
    default_ttl            = 0
    max_ttl                = 60

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.admin_basic_auth.arn
    }
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }

  tags = local.tags
}

resource "aws_s3_bucket_policy" "web_ui" {
  bucket = aws_s3_bucket.web_ui.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid = "AllowCloudFrontServicePrincipalReadOnly"
        Effect = "Allow"
        Principal = {
          Service = "cloudfront.amazonaws.com"
        }
        Action = "s3:GetObject"
        Resource = "${aws_s3_bucket.web_ui.arn}/*"
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.web_ui.arn
          }
        }
      }
    ]
  })
}
