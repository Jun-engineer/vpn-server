data "archive_file" "start_instance" {
  type        = "zip"
  source_file = "${path.module}/../lambda_functions/start_instance.py"
  output_path = "${path.module}/build/start_instance.zip"
}

data "archive_file" "stop_instance" {
  type        = "zip"
  source_file = "${path.module}/../lambda_functions/stop_instance.py"
  output_path = "${path.module}/build/stop_instance.zip"
}

data "archive_file" "check_status" {
  type        = "zip"
  source_file = "${path.module}/../lambda_functions/check_status.py"
  output_path = "${path.module}/build/check_status.zip"
}

data "archive_file" "monitor_traffic" {
  type        = "zip"
  source_file = "${path.module}/../lambda_functions/monitor_traffic.py"
  output_path = "${path.module}/build/monitor_traffic.zip"
}

data "archive_file" "register_peer" {
  type        = "zip"
  source_file = "${path.module}/../lambda_functions/register_peer.py"
  output_path = "${path.module}/build/register_peer.zip"
}

resource "aws_lambda_function" "start_instance" {
  function_name    = "${var.project_name}-start"
  role             = aws_iam_role.lambda.arn
  handler          = "start_instance.handler"
  runtime          = "python3.12"
  filename         = data.archive_file.start_instance.output_path
  source_code_hash = data.archive_file.start_instance.output_base64sha256
  timeout          = 30

  environment {
    variables = merge(local.lambda_env_common, {
      START_NOTIFICATION_TOPIC_ARN = aws_sns_topic.start_notifications.arn
    })
  }
}

resource "aws_lambda_function" "stop_instance" {
  function_name    = "${var.project_name}-stop"
  role             = aws_iam_role.lambda.arn
  handler          = "stop_instance.handler"
  runtime          = "python3.12"
  filename         = data.archive_file.stop_instance.output_path
  source_code_hash = data.archive_file.stop_instance.output_base64sha256
  timeout          = 30

  environment {
    variables = merge(local.lambda_env_common, {
      AUTO_STOP_SOURCE = "manual"
    })
  }
}

resource "aws_lambda_function" "check_status" {
  function_name    = "${var.project_name}-status"
  role             = aws_iam_role.lambda.arn
  handler          = "check_status.handler"
  runtime          = "python3.12"
  filename         = data.archive_file.check_status.output_path
  source_code_hash = data.archive_file.check_status.output_base64sha256
  timeout          = 15

  environment {
    variables = local.lambda_env_common
  }
}

resource "aws_lambda_function" "monitor_traffic" {
  function_name    = "${var.project_name}-monitor"
  role             = aws_iam_role.lambda.arn
  handler          = "monitor_traffic.handler"
  runtime          = "python3.12"
  filename         = data.archive_file.monitor_traffic.output_path
  source_code_hash = data.archive_file.monitor_traffic.output_base64sha256
  timeout          = 60

  environment {
    variables = merge(local.lambda_env_common, {
      AUTO_STOP_SOURCE = "monitor"
    })
  }
}

resource "aws_lambda_function" "register_peer" {
  function_name    = "${var.project_name}-register"
  role             = aws_iam_role.lambda.arn
  handler          = "register_peer.handler"
  runtime          = "python3.12"
  filename         = data.archive_file.register_peer.output_path
  source_code_hash = data.archive_file.register_peer.output_base64sha256
  timeout          = 120
  tracing_config {
    mode = "Active"
  }

  environment {
    variables = local.lambda_env_register
  }
}
