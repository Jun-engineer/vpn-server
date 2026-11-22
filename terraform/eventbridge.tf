# Automatic shutdown schedules are deliberately kept DISABLED.
# The VPN stays running until a user explicitly stops it (or AWS intervenes).
resource "aws_scheduler_schedule" "weekday_stop" {
  name                         = "${var.project_name}-weekday-stop"
  description                  = "Former weekday midnight auto-stop (disabled; VPN stops manually)"
  schedule_expression          = var.weekday_stop_cron_expression
  schedule_expression_timezone = local.timezone_name
  state                        = "DISABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.stop_instance.arn
    role_arn = aws_iam_role.scheduler.arn
    input = jsonencode({
      trigger = "weekday-stop"
    })
  }
}

resource "aws_lambda_permission" "scheduler_weekday_stop" {
  statement_id  = "AllowSchedulerWeekdayStop"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.stop_instance.function_name
  principal     = "scheduler.amazonaws.com"
  source_arn    = aws_scheduler_schedule.weekday_stop.arn
}

resource "aws_scheduler_schedule" "monitor" {
  name                         = "${var.project_name}-monitor"
  description                  = "Former low-traffic auto-stop monitor (disabled; VPN stops manually)"
  schedule_expression          = var.monitor_schedule_expression
  schedule_expression_timezone = local.timezone_name
  state                        = "DISABLED"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.monitor_traffic.arn
    role_arn = aws_iam_role.scheduler.arn
    input = jsonencode({
      trigger = "monitor"
    })
  }
}

resource "aws_lambda_permission" "scheduler_monitor" {
  statement_id  = "AllowSchedulerMonitor"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.monitor_traffic.function_name
  principal     = "scheduler.amazonaws.com"
  source_arn    = aws_scheduler_schedule.monitor.arn
}
