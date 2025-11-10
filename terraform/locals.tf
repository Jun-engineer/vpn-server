locals {
  tags = {
    Project = var.project_name
  }

  timezone_name          = var.timezone_name
  weekday_start_hour     = var.allowed_weekday_start_hour
  weekday_end_hour       = var.allowed_weekday_end_hour
  monitor_threshold_mb   = var.monitor_threshold_mb_per_hour
  monitor_evaluation_hrs = var.monitor_evaluation_hours
  monitor_period_seconds = var.monitor_period_seconds

  default_bucket_prefix = replace(var.project_name, "_", "-")

  web_bucket_name = var.web_bucket_name != "" ? var.web_bucket_name : format("%s-%s", local.default_bucket_prefix, random_id.web_bucket_suffix.hex)

  vpn_private_ip = var.vpn_private_ip != "" ? var.vpn_private_ip : cidrhost(var.public_subnet_cidr, 10)

  lambda_env_common = {
    INSTANCE_ID          = aws_instance.vpn.id
    TIMEZONE             = local.timezone_name
    WEEKDAY_START_HOUR   = tostring(local.weekday_start_hour)
    WEEKDAY_END_HOUR     = tostring(local.weekday_end_hour)
    MONITOR_THRESHOLD_MB = tostring(local.monitor_threshold_mb)
    MONITOR_WINDOW_HRS   = tostring(local.monitor_evaluation_hrs)
    MONITOR_PERIOD_SECONDS = tostring(local.monitor_period_seconds)
  }
}
