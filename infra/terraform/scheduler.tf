# Nightly full re-render of the crawlable pages (backend/scripts/render_site.py): heals any page
# a failed publish or erasure hook left behind, refreshes llms-full.txt and prunes stale pages.
# Runs the backend task definition once with a different command; no service, no load balancer.

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${local.name}-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

data "aws_iam_policy_document" "scheduler" {
  statement {
    actions   = ["ecs:RunTask"]
    resources = ["${aws_ecs_task_definition.backend.arn_without_revision}:*"]
    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values   = [data.aws_ecs_cluster.default.arn]
    }
  }
  statement {
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.execution.arn, aws_iam_role.task.arn]
  }
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "run-render-site"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler.json
}

resource "aws_scheduler_schedule" "render_site" {
  name                         = "${local.name}-render-site"
  description                  = "Nightly re-render of crawlable business and hub pages"
  schedule_expression          = var.render_site_schedule
  schedule_expression_timezone = "UTC"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = data.aws_ecs_cluster.default.arn
    role_arn = aws_iam_role.scheduler.arn

    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.backend.arn
      launch_type         = "FARGATE"
      platform_version    = "LATEST"
      task_count          = 1

      network_configuration {
        subnets          = data.aws_subnets.public.ids
        security_groups  = [aws_security_group.tasks.id]
        assign_public_ip = true
      }
    }

    input = jsonencode({
      containerOverrides = [{
        name    = "backend"
        command = ["python", "scripts/render_site.py"]
      }]
    })

    retry_policy {
      maximum_retry_attempts = 1
    }
  }
}
