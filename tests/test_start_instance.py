import importlib
import json
import os
from datetime import datetime as real_datetime
from types import SimpleNamespace

import boto3
import pytest
from moto import mock_ec2, mock_sns


def _set_aws_test_credentials(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-1")


def _load_start_module():
    module = importlib.import_module("lambda_functions.start_instance")
    return importlib.reload(module)


def _mock_event(source_ip="198.51.100.10", user_agent="pytest"):
    return {
        "requestContext": {
            "identity": {
                "sourceIp": source_ip,
                "userAgent": user_agent
            },
            "requestId": "unit-test-request"
        }
    }


@pytest.fixture
def moto_environment(monkeypatch):
    _set_aws_test_credentials(monkeypatch)
    monkeypatch.setenv("TIMEZONE", "UTC")
    monkeypatch.setenv("WEEKDAY_START_HOUR", "0")
    monkeypatch.setenv("WEEKDAY_END_HOUR", "24")

    with mock_ec2(), mock_sns():
        ec2_client = boto3.client("ec2")
        sns_client = boto3.client("sns")
        ami_id = ec2_client.register_image(
            Name="vpn-test-ami",
            Architecture="x86_64",
            RootDeviceName="/dev/sda1",
            VirtualizationType="hvm"
        )["ImageId"]
        reservation = ec2_client.run_instances(
            ImageId=ami_id,
            MinCount=1,
            MaxCount=1
        )
        instance_id = reservation["Instances"][0]["InstanceId"]
        monkeypatch.setenv("INSTANCE_ID", instance_id)

        topic_arn = sns_client.create_topic(Name="vpn-start-test")
        monkeypatch.setenv("START_NOTIFICATION_TOPIC_ARN", topic_arn["TopicArn"])

        module = _load_start_module()
        yield module, ec2_client


def test_start_denied_outside_window(monkeypatch, moto_environment):
    module, ec2_client = moto_environment
    module.WEEKDAY_START_HOUR = 13
    module.WEEKDAY_END_HOUR = 18

    class FrozenDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime(2024, 1, 2, 3, tzinfo=tz)  # Tuesday 03:00

    monkeypatch.setattr(module, "datetime", FrozenDateTime)

    publish_calls = []
    monkeypatch.setattr(
        module,
        "sns",
        SimpleNamespace(publish=lambda **kwargs: publish_calls.append(kwargs))
    )

    response = module.handler(_mock_event(), None)
    body = json.loads(response["body"])

    assert response["statusCode"] == 403
    assert "disabled" in body["message"].lower()
    assert publish_calls == []

    # Ensure instance state unchanged
    reservations = ec2_client.describe_instances(InstanceIds=[os.environ["INSTANCE_ID"]])["Reservations"]
    state = reservations[0]["Instances"][0]["State"]["Name"]
    assert state == "running"


def test_start_noop_when_running(monkeypatch, moto_environment):
    module, _ = moto_environment

    publish_calls = []
    monkeypatch.setattr(
        module,
        "sns",
        SimpleNamespace(publish=lambda **kwargs: publish_calls.append(kwargs))
    )

    response = module.handler(_mock_event(), None)
    body = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert body["state"] == "running"
    assert publish_calls == []


def test_start_triggers_notification(monkeypatch, moto_environment):
    module, ec2_client = moto_environment

    # Stop instance so the handler issues a start
    ec2_client.stop_instances(InstanceIds=[os.environ["INSTANCE_ID"]])

    publish_calls = []
    monkeypatch.setattr(
        module,
        "sns",
        SimpleNamespace(publish=lambda **kwargs: publish_calls.append(kwargs) or {"MessageId": "1"})
    )

    response = module.handler(_mock_event(), None)
    body = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert body["state"] == "pending"
    assert len(publish_calls) == 1
    assert publish_calls[0]["TopicArn"] == os.environ["START_NOTIFICATION_TOPIC_ARN"]
    message = json.loads(publish_calls[0]["Message"])
    assert message["instanceId"] == os.environ["INSTANCE_ID"]
    assert "sourceIp" in message