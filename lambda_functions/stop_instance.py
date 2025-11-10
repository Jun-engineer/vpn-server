import json
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import boto3

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

ec2 = boto3.client("ec2")

INSTANCE_ID = os.environ["INSTANCE_ID"]
TIMEZONE = ZoneInfo(os.environ.get("TIMEZONE", "UTC"))

DEFAULT_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,X-Api-Key",
    "Access-Control-Allow-Methods": "OPTIONS,GET,POST"
}


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


def handler(event, context):
    try:
        trigger = event.get("trigger") or event.get("source") or "api"
        LOGGER.info("Stop request trigger=%s", trigger)

        current_state = _current_state()
        LOGGER.info("Current instance state: %s", current_state)

        if current_state in {"stopping", "stopped"}:
            return _response(200, {
                "message": "Instance is already stopping or stopped.",
                "state": current_state,
                "trigger": trigger
            })

        ec2.stop_instances(InstanceIds=[INSTANCE_ID])
        return _response(200, {
            "message": "Stop command issued successfully.",
            "state": "stopping",
            "trigger": trigger,
            "timestampLocal": datetime.now(TIMEZONE).isoformat()
        })
    except Exception as exc:
        LOGGER.exception("Failed to stop instance: %s", exc)
        return _response(500, {
            "message": "Failed to stop instance.",
            "error": str(exc)
        })
