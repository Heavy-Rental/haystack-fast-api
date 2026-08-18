#!/usr/bin/env python3
"""Dynamic inventory: InService asg-haystack guests only. Connection is SSM."""
from __future__ import annotations

import json
import subprocess
import sys

ASGS = {
    "asg-haystack": "haystack",
}


def aws_json(args: list[str]):
    out = subprocess.check_output(["aws", *args], text=True)
    return json.loads(out)


def empty_inventory() -> dict:
    return {"_meta": {"hostvars": {}}, "haystack": {"hosts": []}}


def build() -> dict:
    inv = empty_inventory()
    for asg, group in ASGS.items():
        try:
            data = aws_json(
                [
                    "autoscaling",
                    "describe-auto-scaling-groups",
                    "--auto-scaling-group-names",
                    asg,
                ]
            )
        except subprocess.CalledProcessError:
            continue
        groups = data.get("AutoScalingGroups") or []
        if not groups:
            continue
        for inst in groups[0].get("Instances") or []:
            if inst.get("LifecycleState") != "InService":
                continue
            iid = inst["InstanceId"]
            inv[group]["hosts"].append(iid)
            inv["_meta"]["hostvars"][iid] = {
                "ansible_host": iid,
                "ansible_connection": "amazon.aws.aws_ssm",
                "ansible_aws_ssm_region": "us-east-1",
                "ansible_user": "ssm-user",
                "asg_name": asg,
                "app_role": group,
                "app_secret_id": f"heavy-rental/{group}",
            }
    return inv


def main() -> None:
    if len(sys.argv) == 2 and sys.argv[1] == "--list":
        print(json.dumps(build()))
        return
    if len(sys.argv) == 3 and sys.argv[1] == "--host":
        inv = build()
        print(json.dumps(inv["_meta"]["hostvars"].get(sys.argv[2], {})))
        return
    print(json.dumps(build()))


if __name__ == "__main__":
    main()
