# ---------------------------------------------------------------------------
# Security groups
# ---------------------------------------------------------------------------

resource "aws_security_group" "alb" {
  name        = "${local.name}-alb"
  description = "afefehub API load balancer"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description      = "HTTP"
    from_port        = 80
    to_port          = 80
    protocol         = "tcp"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  ingress {
    description      = "HTTPS"
    from_port        = 443
    to_port          = 443
    protocol         = "tcp"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  egress {
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }
}

resource "aws_security_group" "tasks" {
  name        = "${local.name}-backend-tasks"
  description = "afefehub backend Fargate tasks"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description     = "App port from ALB only"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }
}

# ---------------------------------------------------------------------------
# Application load balancer
# ---------------------------------------------------------------------------

resource "aws_lb" "api" {
  name                       = "${local.name}-api"
  load_balancer_type         = "application"
  internal                   = false
  security_groups            = [aws_security_group.alb.id]
  subnets                    = data.aws_subnets.public.ids
  drop_invalid_header_fields = true
  idle_timeout               = 60
}

resource "aws_lb_target_group" "backend" {
  name                 = "${local.name}-backend"
  port                 = 8000
  protocol             = "HTTP"
  target_type          = "ip"
  vpc_id               = data.aws_vpc.default.id
  deregistration_delay = 30

  health_check {
    path                = "/healthz"
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

# Before the nameserver cutover (no certificate yet) port 80 forwards straight
# to the backend so the target group is attached to the ALB and the service can
# exist. Once dns_delegated = true it becomes a permanent redirect to HTTPS.
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.api.arn
  port              = 80
  protocol          = "HTTP"

  dynamic "default_action" {
    for_each = var.dns_delegated ? [1] : []
    content {
      type = "redirect"
      redirect {
        port        = "443"
        protocol    = "HTTPS"
        status_code = "HTTP_301"
      }
    }
  }

  dynamic "default_action" {
    for_each = var.dns_delegated ? [] : [1]
    content {
      type             = "forward"
      target_group_arn = aws_lb_target_group.backend.arn
    }
  }
}

resource "aws_lb_listener" "https" {
  count = var.dns_delegated ? 1 : 0

  load_balancer_arn = aws_lb.api.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate_validation.api[0].certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend.arn
  }
}

# ---------------------------------------------------------------------------
# Logs, task definition, service
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "backend" {
  name              = local.log_group_name
  retention_in_days = 14
}

resource "aws_ecs_task_definition" "backend" {
  family                   = "${local.name}-backend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  # Scratch space for downloaded reels, ffmpeg output and voice notes. Sized so a few
  # max_reel_bytes downloads in flight cannot exhaust it; the app cleans up per submission.
  ephemeral_storage {
    size_in_gib = 30
  }

  volume {
    name = "tmp"
  }

  container_definitions = jsonencode([
    {
      name      = "backend"
      image     = local.backend_image
      essential = true

      # The image runs as uid 10001; only /tmp (the volume below) is writable.
      user                   = "10001:10001"
      readonlyRootFilesystem = true
      mountPoints = [{
        sourceVolume  = "tmp"
        containerPath = "/tmp"
        readOnly      = false
      }]
      linuxParameters = {
        capabilities = { drop = ["ALL"] }
      }

      portMappings = [{
        containerPort = 8000
        hostPort      = 8000
        protocol      = "tcp"
      }]

      environment = [for k, v in local.backend_env : { name = k, value = v }]

      secrets = [for n in var.secret_names : {
        name      = n
        valueFrom = aws_ssm_parameter.secrets[n].arn
      }]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.backend.name
          "awslogs-region"        = local.region
          "awslogs-stream-prefix" = "ecs"
        }
      }
    }
  ])
}

resource "aws_ecs_service" "backend" {
  name                              = "${local.name}-backend"
  cluster                           = data.aws_ecs_cluster.default.arn
  task_definition                   = aws_ecs_task_definition.backend.arn
  desired_count                     = var.desired_count
  launch_type                       = "FARGATE"
  platform_version                  = "LATEST"
  health_check_grace_period_seconds = 60
  enable_execute_command            = true

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets          = data.aws_subnets.public.ids
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "backend"
    container_port   = 8000
  }

  depends_on = [
    aws_lb_listener.http,
    aws_iam_role_policy.task,
    aws_iam_role_policy_attachment.execution,
    aws_iam_role_policy.execution_secrets,
  ]
}
