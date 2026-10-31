# ---------------------------------------------------------------------------
# WAF in front of the API load balancer.
#
# The in-process token bucket in app/api/public.py resets on every deploy and multiplies with
# the task count, so the real cap on paid Google / Muse Spark calls has to live at the edge.
# The WhatsApp webhook is excluded from every rule: Meta delivers from a small set of IPs and
# a false positive there means lost reviews.
# ---------------------------------------------------------------------------

locals {
  waf_metric_prefix = "${local.name}Api"
}

resource "aws_wafv2_web_acl" "api" {
  name        = "${local.name}-api"
  description = "Rate limits and managed rules for ${local.api_domain}"
  scope       = "REGIONAL"

  default_action {
    allow {}
  }

  # 1. Tight limit on the endpoints that cost money per request.
  rule {
    name     = "places-rate-limit"
    priority = 1

    action {
      block {
        custom_response {
          response_code = 429
        }
      }
    }

    statement {
      rate_based_statement {
        limit                 = var.waf_places_rate_limit
        evaluation_window_sec = 300
        aggregate_key_type    = "IP"

        scope_down_statement {
          byte_match_statement {
            search_string         = "/api/places/"
            positional_constraint = "STARTS_WITH"
            field_to_match {
              uri_path {}
            }
            text_transformation {
              priority = 0
              type     = "LOWERCASE"
            }
          }
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${local.waf_metric_prefix}PlacesRateLimit"
      sampled_requests_enabled   = true
    }
  }

  # 2. Looser limit on the rest of the public read API (search, business pages, audio).
  rule {
    name     = "api-rate-limit"
    priority = 2

    action {
      block {
        custom_response {
          response_code = 429
        }
      }
    }

    statement {
      rate_based_statement {
        limit                 = var.waf_api_rate_limit
        evaluation_window_sec = 300
        aggregate_key_type    = "IP"

        scope_down_statement {
          byte_match_statement {
            search_string         = "/api/"
            positional_constraint = "STARTS_WITH"
            field_to_match {
              uri_path {}
            }
            text_transformation {
              priority = 0
              type     = "LOWERCASE"
            }
          }
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${local.waf_metric_prefix}RateLimit"
      sampled_requests_enabled   = true
    }
  }

  # 3. AWS managed baseline (bad bots, request smuggling, oversize bodies, ...), everywhere
  #    except the webhook path.
  rule {
    name     = "aws-common"
    priority = 3

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"

        scope_down_statement {
          not_statement {
            statement {
              byte_match_statement {
                search_string         = "/webhooks/"
                positional_constraint = "STARTS_WITH"
                field_to_match {
                  uri_path {}
                }
                text_transformation {
                  priority = 0
                  type     = "LOWERCASE"
                }
              }
            }
          }
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${local.waf_metric_prefix}Common"
      sampled_requests_enabled   = true
    }
  }

  # 4. Known malicious IPs (AWS threat intel), including on the webhook path.
  rule {
    name     = "aws-ip-reputation"
    priority = 4

    override_action {
      none {}
    }

    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesAmazonIpReputationList"
        vendor_name = "AWS"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${local.waf_metric_prefix}IpReputation"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = local.waf_metric_prefix
    sampled_requests_enabled   = true
  }
}

resource "aws_wafv2_web_acl_association" "api" {
  resource_arn = aws_lb.api.arn
  web_acl_arn  = aws_wafv2_web_acl.api.arn
}
