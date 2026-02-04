import boto3
import logging
from datetime import datetime, timedelta
import os
# --- CONFIGURATION ---
TARGET_TAG_KEY = 'env'      # UPDATED to lowercase based on your test
TARGET_TAG_VALUE = 'Test'
MAX_CPU_THRESHOLD = 5.0     # Raised to 5% to make sure we catch your idle server
DAYS_TO_LOOK_BACK = 7

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ec2 = boto3.client('ec2')
cloudwatch = boto3.client('cloudwatch')
sns = boto3.client('sns')

def get_test_instances():
    print(f" Scanning for instances with tag {TARGET_TAG_KEY}={TARGET_TAG_VALUE}...")
    response = ec2.describe_instances(
        Filters=[
            {'Name': f'tag:{TARGET_TAG_KEY}', 'Values': [TARGET_TAG_VALUE]},
            {'Name': 'instance-state-name', 'Values': ['running']}
        ]
    )
    candidates = []
    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            candidates.append({
                'id': instance['InstanceId'],
                'tags': instance.get('Tags', [])
            })
    return candidates

def is_protected(tags):
    for tag in tags:
        if tag['Key'] == 'Protected' and tag['Value'] == 'True':
            return True
    return False

def get_max_cpu(instance_id):
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(days=DAYS_TO_LOOK_BACK)
    try:
        response = cloudwatch.get_metric_statistics(
            Namespace='AWS/EC2',
            MetricName='CPUUtilization',
            Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
            StartTime=start_time,
            EndTime=end_time,
            Period=86400 * DAYS_TO_LOOK_BACK, 
            Statistics=['Maximum']
        )
        if response['Datapoints']:
            return response['Datapoints'][0]['Maximum']
        else:
            return 0.0 
    except Exception as e:
        print(f"Error fetching metrics: {e}")
        return -1

def lambda_handler(event, context):
    candidates = get_test_instances()
    stopped_instances = []

    print(f"Found {len(candidates)} instances.")

    for instance in candidates:
        instance_id = instance['id']
        
        if is_protected(instance['tags']):
            print(f"SKIPPING {instance_id}: Protected tag found.")
            continue
        
        max_cpu = get_max_cpu(instance_id)
        print(f"Instance: {instance_id} | Max CPU: {max_cpu}%")
        
        if max_cpu < MAX_CPU_THRESHOLD:
            print(f"ZOMBIE DETECTED: {instance_id}")
            try:
                print(f"Stopping instance {instance_id}...")
                ec2.stop_instances(InstanceIds=[instance_id])
                stopped_instances.append(instance_id)
                print("SUCCESS: Instance stopped.")
            except Exception as e:
                print(f"FAILED to stop: {e}")
        else:
            print("Active. Instance is in use.")

    # ----- SEND NOTIFICATION -----
    message = {
        "total_found": len(candidates),
        "stopped_instances": stopped_instances,
        "timestamp": str(datetime.utcnow())
    }

    sns.publish(
        TopicArn=os.environ["SNS_TOPIC_ARN"],
        Message=str(message),
        Subject="Daily EC2 Cleanup Report"
    )

    return {
        "status": "Job Complete",
        "stopped": stopped_instances
    }