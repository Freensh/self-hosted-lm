"""Let the AWS assistant list Astra instances using its read-only IAM role."""

import boto3


def list_instances():
    ec2 = boto3.client("ec2", region_name="us-east-1")
    instances = []
    pages = ec2.get_paginator("describe_instances").paginate(
        Filters=[{"Name": "tag:Project", "Values": ["astra"]}],
        PaginationConfig={"MaxItems": 50},
    )
    for page in pages:
        for reservation in page["Reservations"]:
            for instance in reservation["Instances"]:
                instances.append(
                    {
                        "id": instance["InstanceId"],
                        "state": instance["State"]["Name"],
                        "type": instance["InstanceType"],
                    }
                )
    return instances
