import boto3

def list_instances():
    ec2 = boto3.client("ec2", region_name="us-east-1")
    result = []
    pages = ec2.get_paginator("describe_instances").paginate(
        Filters=[{"Name": "tag:Project", "Values": ["astra"]}],
        PaginationConfig={"MaxItems": 50})
    for page in pages:
        for reservation in page["Reservations"]:
            for instance in reservation["Instances"]:
                result.append({"id": instance["InstanceId"],
                               "state": instance["State"]["Name"],
                               "type": instance["InstanceType"]})
    return result
