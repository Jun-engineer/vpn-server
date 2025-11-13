import json
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import boto3

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

INSTANCE_ID = os.environ["INSTANCE_ID"]
TIMEZONE = ZoneInfo(os.environ.get("TIMEZONE", "UTC"))
WEEKDAY_START_HOUR = int(os.environ.get("WEEKDAY_START_HOUR", 13))
WEEKDAY_END_HOUR = int(os.environ.get("WEEKDAY_END_HOUR", 24))
NOTIFICATION_TOPIC_ARN = os.environ.get("START_NOTIFICATION_TOPIC_ARN", "")

DEFAULT_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,X-Api-Key",
    "Access-Control-Allow-Methods": "OPTIONS,GET,POST"
}

ec2 = boto3.client("ec2")
sns = boto3.client("sns")


def _response(status: int, data: dict) -> dict:
    return {
        "statusCode": status,
        "headers": DEFAULT_HEADERS,
        "body": json.dumps(data, ensure_ascii=False)
    }


def _current_state() -> str:
    reservations = ec2.describe_instances(InstanceIds=[INSTANCE_ID])["Reservations"]
    instances = [instance for r in reservations for instance in r.get("Instances", [])]
    if not instances:
        raise RuntimeError("Instance metadata not found")
    return instances[0]["State"]["Name"]


def _extract_request_details(event: dict) -> dict:
    request_context = {}
    if isinstance(event, dict):
        request_context = event.get("requestContext", {}) or {}

    identity = request_context.get("identity", {}) or {}
    http_ctx = request_context.get("http", {}) or {}

    return {
        "sourceIp": identity.get("sourceIp") or http_ctx.get("sourceIp"),
        "userAgent": identity.get("userAgent") or http_ctx.get("userAgent"),
        "requestId": request_context.get("requestId") or request_context.get("requestId")
    }


def _publish_start_event(request_meta: dict) -> None:
    if not NOTIFICATION_TOPIC_ARN:
        return

    now_iso = datetime.now(TIMEZONE).isoformat()
    body = {
        "message": "VPN start initiated",
        "instanceId": INSTANCE_ID,
        "timestamp": now_iso,
        "sourceIp": request_meta.get("sourceIp"),
        "userAgent": request_meta.get("userAgent"),
        "requestId": request_meta.get("requestId")
    }

    try:
        sns.publish(
            TopicArn=NOTIFICATION_TOPIC_ARN,
            Subject="VPN start requested",
            Message=json.dumps(body, ensure_ascii=False)
        )
    except Exception as exc:  # pylint: disable=broad-except
        LOGGER.exception("Failed to publish start notification: %s", exc)


def handler(event, context):
    try:
        now = datetime.now(TIMEZONE)
        LOGGER.info("Start request received at %s", now.isoformat())

        if now.weekday() < 5:
            if not (WEEKDAY_START_HOUR <= now.hour < WEEKDAY_END_HOUR):
                return _response(403, {
                    "message": "VPN start is disabled until 13:00 Australia/Sydney on weekdays.",
                    "currentHourLocal": now.hour,
                    "allowedHoursLocal": [WEEKDAY_START_HOUR, WEEKDAY_END_HOUR]
                })

        current_state = _current_state()
        LOGGER.info("Current instance state: %s", current_state)

        if current_state in {"pending", "running"}:
            return _response(200, {
                "message": "Instance is already running.",
                "state": current_state
            })

        request_meta = _extract_request_details(event)
        ec2.start_instances(InstanceIds=[INSTANCE_ID])
        _publish_start_event(request_meta)
        return _response(200, {
            "message": "Start command issued successfully.",
            "state": "pending"
        })
    except Exception as exc:
        LOGGER.exception("Failed to start instance: %s", exc)
        return _response(500, {
            "message": "Failed to start instance.",
            "error": str(exc)
        })
