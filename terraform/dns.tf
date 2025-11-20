resource "aws_route53_zone" "web_ui" {
  count = local.custom_domain_enabled ? 1 : 0

  name = var.web_custom_domain
  tags = local.tags
}

resource "aws_acm_certificate" "web_ui" {
  count = local.custom_domain_enabled ? 1 : 0

  provider          = aws.us_east_1
  domain_name       = var.web_custom_domain
  validation_method = "DNS"
  tags              = local.tags

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "web_ui_cert_validation" {
  for_each = local.custom_domain_enabled ? {
    for dvo in aws_acm_certificate.web_ui[0].domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      record = dvo.resource_record_value
      type   = dvo.resource_record_type
    }
  } : {}

  zone_id = aws_route53_zone.web_ui[0].zone_id
  name    = each.value.name
  type    = each.value.type
  ttl     = 60
  records = [each.value.record]
}

resource "aws_acm_certificate_validation" "web_ui" {
  count = local.custom_domain_enabled ? 1 : 0

  provider = aws.us_east_1

  certificate_arn         = aws_acm_certificate.web_ui[0].arn
  validation_record_fqdns = [for record in aws_route53_record.web_ui_cert_validation : record.fqdn]
}

resource "aws_route53_record" "web_ui_alias_a" {
  count = local.custom_domain_enabled ? 1 : 0

  zone_id = aws_route53_zone.web_ui[0].zone_id
  name    = var.web_custom_domain
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.web_ui.domain_name
    zone_id                = aws_cloudfront_distribution.web_ui.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "web_ui_alias_aaaa" {
  count = local.custom_domain_enabled ? 1 : 0

  zone_id = aws_route53_zone.web_ui[0].zone_id
  name    = var.web_custom_domain
  type    = "AAAA"

  alias {
    name                   = aws_cloudfront_distribution.web_ui.domain_name
    zone_id                = aws_cloudfront_distribution.web_ui.hosted_zone_id
    evaluate_target_health = false
  }
}
