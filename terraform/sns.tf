resource "aws_sns_topic" "start_notifications" {
  name = "${var.project_name}-start-events"
  tags = local.tags
}

resource "aws_sns_topic_subscription" "start_notification_emails" {
  for_each = toset(var.start_notification_emails)

  topic_arn = aws_sns_topic.start_notifications.arn
  protocol  = "email"
  endpoint  = each.value
}
