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
  wireguard_client_subnet = var.wireguard_client_subnet
  wireguard_server_address = var.wireguard_server_address
  wireguard_interface_name = var.wireguard_interface_name
  wireguard_config_path    = var.wireguard_config_path
  register_command_timeout = var.register_command_timeout_seconds
  admin_basic_auth_header  = "Basic ${base64encode("${var.admin_basic_auth_username}:${var.admin_basic_auth_password}")}"

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

  lambda_env_register = merge(local.lambda_env_common, {
    CLIENT_SUBNET_CIDR          = local.wireguard_client_subnet
    SERVER_ADDRESS              = local.wireguard_server_address
    WG_INTERFACE                = local.wireguard_interface_name
    WG_CONF_PATH                = local.wireguard_config_path
    SSM_COMMAND_TIMEOUT_SECONDS = tostring(local.register_command_timeout)
  })
}
