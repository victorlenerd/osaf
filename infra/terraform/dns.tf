# ---------------------------------------------------------------------------
# Hosted zone + the records GoDaddy serves today (so Zoho mail keeps working)
# ---------------------------------------------------------------------------

resource "aws_route53_zone" "main" {
  name    = var.domain
  comment = "${var.domain} - managed by Terraform (infra/terraform)"
}

resource "aws_route53_record" "mx" {
  zone_id = aws_route53_zone.main.zone_id
  name    = var.domain
  type    = "MX"
  ttl     = 3600
  records = [
    "10 mx.zoho.com.",
    "20 mx2.zoho.com.",
    "50 mx3.zoho.com.",
  ]
}

resource "aws_route53_record" "spf_apex" {
  zone_id = aws_route53_zone.main.zone_id
  name    = var.domain
  type    = "TXT"
  ttl     = 3600
  records = ["v=spf1 include:${var.zoho_spf_selector}.${var.domain} ~all"]
}

resource "aws_route53_record" "spf_zoho" {
  zone_id = aws_route53_zone.main.zone_id
  name    = "${var.zoho_spf_selector}.${var.domain}"
  type    = "TXT"
  ttl     = 3600
  records = ["v=spf1 include:zohomail.com ~all"]
}

# Route53 limits a single TXT string to 255 chars; longer values are written as
# several quoted chunks ("aaa""bbb") which resolvers concatenate.
resource "aws_route53_record" "dkim_zoho" {
  zone_id = aws_route53_zone.main.zone_id
  name    = "zmail._domainkey.${var.domain}"
  type    = "TXT"
  ttl     = 3600
  records = [join("\"\"", regexall(".{1,255}", var.zoho_dkim_value))]
}

# ---------------------------------------------------------------------------
# Site: apex + www -> Lovable (today) or CloudFront (after cutover)
# ---------------------------------------------------------------------------

resource "aws_route53_record" "site_lovable" {
  for_each = var.site_dns_target == "lovable" ? toset(local.site_domains) : toset([])

  zone_id = aws_route53_zone.main.zone_id
  name    = each.value
  type    = "A"
  ttl     = 300
  records = [var.lovable_ip]
}

resource "aws_route53_record" "site_cloudfront" {
  for_each = var.site_dns_target == "cloudfront" ? toset(local.site_domains) : toset([])

  zone_id = aws_route53_zone.main.zone_id
  name    = each.value
  type    = "A"

  alias {
    name                   = aws_cloudfront_distribution.site[0].domain_name
    zone_id                = aws_cloudfront_distribution.site[0].hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "site_cloudfront_ipv6" {
  for_each = var.site_dns_target == "cloudfront" ? toset(local.site_domains) : toset([])

  zone_id = aws_route53_zone.main.zone_id
  name    = each.value
  type    = "AAAA"

  alias {
    name                   = aws_cloudfront_distribution.site[0].domain_name
    zone_id                = aws_cloudfront_distribution.site[0].hosted_zone_id
    evaluate_target_health = false
  }
}

# ---------------------------------------------------------------------------
# API: api.<domain> -> ALB
# ---------------------------------------------------------------------------

resource "aws_route53_record" "api" {
  zone_id = aws_route53_zone.main.zone_id
  name    = local.api_domain
  type    = "A"

  alias {
    name                   = aws_lb.api.dns_name
    zone_id                = aws_lb.api.zone_id
    evaluate_target_health = true
  }
}

# ---------------------------------------------------------------------------
# ACM certificates (DNS validated). The certificate + validation records are
# created right away; the *validation* resources (which block until ACM sees
# the records) only exist once dns_delegated = true.
# ---------------------------------------------------------------------------

resource "aws_acm_certificate" "site" {
  domain_name               = var.domain
  subject_alternative_names = [local.www_domain]
  validation_method         = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "site_cert_validation" {
  for_each = toset(local.site_domains)

  allow_overwrite = true
  zone_id         = aws_route53_zone.main.zone_id
  ttl             = 60
  name            = one([for dvo in aws_acm_certificate.site.domain_validation_options : dvo.resource_record_name if dvo.domain_name == each.key])
  type            = one([for dvo in aws_acm_certificate.site.domain_validation_options : dvo.resource_record_type if dvo.domain_name == each.key])
  records         = [one([for dvo in aws_acm_certificate.site.domain_validation_options : dvo.resource_record_value if dvo.domain_name == each.key])]
}

resource "aws_acm_certificate_validation" "site" {
  count = var.dns_delegated ? 1 : 0

  certificate_arn         = aws_acm_certificate.site.arn
  validation_record_fqdns = [for r in aws_route53_record.site_cert_validation : r.fqdn]
}

resource "aws_acm_certificate" "api" {
  domain_name       = local.api_domain
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "api_cert_validation" {
  for_each = toset([local.api_domain])

  allow_overwrite = true
  zone_id         = aws_route53_zone.main.zone_id
  ttl             = 60
  name            = one([for dvo in aws_acm_certificate.api.domain_validation_options : dvo.resource_record_name if dvo.domain_name == each.key])
  type            = one([for dvo in aws_acm_certificate.api.domain_validation_options : dvo.resource_record_type if dvo.domain_name == each.key])
  records         = [one([for dvo in aws_acm_certificate.api.domain_validation_options : dvo.resource_record_value if dvo.domain_name == each.key])]
}

resource "aws_acm_certificate_validation" "api" {
  count = var.dns_delegated ? 1 : 0

  certificate_arn         = aws_acm_certificate.api.arn
  validation_record_fqdns = [for r in aws_route53_record.api_cert_validation : r.fqdn]
}
