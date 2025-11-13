variable "project_name" {
  description = "Project identifier used for tagging resources."
  type        = string
  default     = "vpn-server-tokyo"
}

variable "aws_region" {
  description = "AWS region for all resources."
  type        = string
  default     = "ap-northeast-1"
}

variable "timezone_name" {
  description = "Primary timezone for scheduling and access control."
  type        = string
  default     = "Australia/Sydney"
}

variable "vpn_ami_id" {
  description = "AMI ID containing the preconfigured WireGuard environment."
  type        = string
  default     = "ami-0f52389a8648b923a"
}

variable "vpn_instance_type" {
  description = "Instance type for the VPN EC2 server. Ensure it matches the AMI architecture."
  type        = string
  default     = "t3a.small"
}

variable "vpc_cidr" {
  description = "CIDR block for the dedicated VPN VPC."
  type        = string
  default     = "10.10.0.0/16"
}

variable "public_subnet_cidr" {
  description = "CIDR block for the public subnet hosting the VPN instance."
  type        = string
  default     = "10.10.1.0/24"
}

variable "public_subnet_az" {
  description = "Availability Zone for the public subnet."
  type        = string
  default     = "ap-northeast-1a"
}

variable "vpn_private_ip" {
  description = "Optional fixed private IP for the VPN ENI. Leave blank to auto-select within the subnet."
  type        = string
  default     = ""
}

variable "ssh_key_pair_name" {
  description = "Name for the generated EC2 key pair."
  type        = string
  default     = "vpn-server-tokyo-key"
}

variable "allowed_weekday_start_hour" {
  description = "Hour in JST when non-admin users may start the VPN instance on weekdays."
  type        = number
  default     = 13
}

variable "allowed_weekday_end_hour" {
  description = "Hour in JST after which the VPN instance should stop allowing starts (24 for end-of-day)."
  type        = number
  default     = 24
}

variable "monitor_schedule_expression" {
  description = "EventBridge Scheduler cron expression (interpreted in timezone_name) for monitoring VPN traffic."
  type        = string
  default     = "cron(0/15 * * * ? *)"
}

variable "weekday_stop_cron_expression" {
  description = "EventBridge Scheduler cron expression (interpreted in timezone_name) for the automatic weekday stop event."
  type        = string
  default     = "cron(0 0 ? * MON-FRI *)"
}

variable "monitor_threshold_mb_per_hour" {
  description = "Average combined network traffic threshold in MB per hour that triggers an automatic stop when undercut for the evaluation window."
  type        = number
  default     = 1
}

variable "monitor_evaluation_hours" {
  description = "Number of trailing hours with low traffic required before the VPN instance is stopped automatically."
  type        = number
  default     = 1.5
}

variable "monitor_period_seconds" {
  description = "CloudWatch metric period in seconds for traffic evaluation."
  type        = number
  default     = 900
}

variable "wireguard_client_subnet" {
  description = "CIDR block containing WireGuard client addresses."
  type        = string
  default     = "192.168.100.0/24"
}

variable "wireguard_server_address" {
  description = "WireGuard server interface address (without CIDR)."
  type        = string
  default     = "192.168.100.1"
}

variable "wireguard_interface_name" {
  description = "WireGuard interface name on the EC2 host."
  type        = string
  default     = "wg0"
}

variable "wireguard_config_path" {
  description = "Absolute path to the WireGuard configuration file on the EC2 host."
  type        = string
  default     = "/etc/wireguard/wg0.conf"
}

variable "register_command_timeout_seconds" {
  description = "Timeout in seconds for the SSM registration command to complete."
  type        = number
  default     = 120
}

variable "admin_basic_auth_username" {
  description = "Username required to access admin.html via CloudFront basic authentication."
  type        = string
  default     = "admin"
}

variable "admin_basic_auth_password" {
  description = "Password required to access admin.html via CloudFront basic authentication."
  type        = string
  default     = "changeme123!"
}

variable "web_bucket_name" {
  description = "Optional custom S3 bucket name for the Web UI. Leave blank to auto-generate."
  type        = string
  default     = ""
}

variable "api_usage_plan_name" {
  description = "Name for the API Gateway usage plan."
  type        = string
  default     = "vpn-control-plan"
}

variable "api_key_name" {
  description = "Name for the generated API key protecting the control API."
  type        = string
  default     = "vpn-control-api-key"
}

variable "allowed_api_quota" {
  description = "Monthly request quota for the API usage plan."
  type        = number
  default     = 1000
}

variable "allowed_api_rate" {
  description = "Burst request limit per second for the API usage plan."
  type        = number
  default     = 5
}

variable "allowed_api_burst" {
  description = "Maximum concurrent request burst allowed by the usage plan."
  type        = number
  default     = 10
}
