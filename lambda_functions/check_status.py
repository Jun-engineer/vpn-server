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


def handler(event, context):
    try:
        reservations = ec2.describe_instances(InstanceIds=[INSTANCE_ID])["Reservations"]
        instances = [instance for r in reservations for instance in r.get("Instances", [])]
        if not instances:
            raise RuntimeError("Instance metadata not found")

        instance = instances[0]
        status_resp = ec2.describe_instance_status(InstanceIds=[INSTANCE_ID], IncludeAllInstances=True)
        status_details = status_resp.get("InstanceStatuses", [{}])
        status_entry = status_details[0] if status_details else {}

        system_status = status_entry.get("SystemStatus", {})
        instance_status = status_entry.get("InstanceStatus", {})

        def _status_is_ok(status: str | None) -> bool:
            return status in {"ok", "passed"}

        status_checks_passed = (
            instance["State"]["Name"] == "running"
            and _status_is_ok(system_status.get("Status"))
            and _status_is_ok(instance_status.get("Status"))
        )

        response_payload = {
            "instanceId": INSTANCE_ID,
            "state": instance["State"]["Name"],
            "publicIp": instance.get("PublicIpAddress"),
            "privateIp": instance.get("PrivateIpAddress"),
            "availabilityZone": instance.get("Placement", {}).get("AvailabilityZone"),
            "systemStatus": system_status.get("Status"),
            "instanceStatus": instance_status.get("Status"),
            "statusChecksPassed": status_checks_passed,
            "timestampLocal": datetime.now(TIMEZONE).isoformat()
        }

        return _response(200, response_payload)
    except Exception as exc:
        LOGGER.exception("Failed to fetch status: %s", exc)
        return _response(500, {
            "message": "Failed to retrieve instance status.",
            "error": str(exc)
        })
