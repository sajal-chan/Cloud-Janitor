# AWS Lambda & Boto3 Study Guide for Cloud Janitor

A practical guide to understand AWS Lambda and Boto3 just enough to build your Cloud Janitor project.

---

## Part 1: AWS Lambda Basics

### What is AWS Lambda?

Lambda is a **serverless compute service**. Instead of managing servers, you write code that runs in response to events or on a schedule.

**Key concept for your project:** Lambda functions are perfect for periodic tasks like "check for idle instances every day at 2 AM."

### Lambda Function Structure (Python)

Every Lambda function has this basic structure:

```python
def lambda_handler(event, context):
    """
    event: Data passed to the function (from EventBridge, S3, API Gateway, etc.)
    context: Metadata about the Lambda execution (request ID, function name, etc.)
    """
    print("This runs in CloudWatch logs")
    return {
        "statusCode": 200,
        "body": "Function executed"
    }
```

**For your project:** Your Lambda function will be triggered by EventBridge (scheduler), so you won't need to use `event` much initially.

### How Lambda Permissions Work (IAM Role)

Lambda functions need an **IAM Role** that grants permissions to AWS services.

**What this means:** Without permissions, Boto3 calls will fail silently or with access denied errors.

**For your project:**
- Your Lambda's IAM Role needs `ec2:DescribeInstances` to read EC2 data.
- Later, it needs `ec2:StopInstances` to stop instances.
- It needs `cloudwatch:GetMetricData` to fetch CPU metrics.

**Key insight:** The IAM Role is attached to the Lambda function, not the code. Boto3 automatically uses the role's permissions when you call AWS APIs.

---

## Part 2: Boto3 Essentials

### What is Boto3?

Boto3 is the **AWS SDK for Python**. It lets you write Python code that interacts with AWS services.

**Installation:**
```bash
pip install boto3
```

### Creating a Client (The Main Pattern)

```python
import boto3

# Create a client for EC2 service
ec2_client = boto3.client('ec2', region_name='us-east-1')

# Create a client for CloudWatch
cloudwatch_client = boto3.client('cloudwatch', region_name='us-east-1')
```

**Key point:** You create separate clients for each AWS service you need.

### EC2 Client: Core Methods for Your Project

#### 1. **Get All EC2 Instances**

```python
ec2_client = boto3.client('ec2', region_name='us-east-1')

response = ec2_client.describe_instances()

# The response is nested; here's how to loop through it:
for reservation in response['Reservations']:
    for instance in reservation['Instances']:
        instance_id = instance['InstanceId']
        state = instance['State']['Name']  # 'running', 'stopped', etc.
        
        # Get tags (if they exist)
        tags = {}
        if 'Tags' in :
            for tag in instaninstancece['Tags']:
                tags[tag['Key']] = tag['Value']
        
        print(f"Instance {instance_id}: {state}, Tags: {tags}")
```

**What to remember:** 
- AWS responses are nested dictionaries. Use `response['Reservations']` → `['Instances']` → individual instance.
- Tags are stored as a list of `{'Key': '...', 'Value': '...'}` dicts. Convert to a simple dict for easier access.

#### 2. **Filter Instances While Describing**

Instead of getting *all* instances and filtering in Python, filter at the API level (faster, cheaper):

```python
# Get only running instances with 'Env=Test' tag
response = ec2_client.describe_instances(
    Filters=[
        {'Name': 'instance-state-name', 'Values': ['running']},
        {'Name': 'tag:Env', 'Values': ['Test']}
    ]
)

# Now loop through only the filtered results
for reservation in response['Reservations']:
    for instance in reservation['Instances']:
        print(f"Found test instance: {instance['InstanceId']}")
```

**For your project:** This is how you find instances with `Env=Test` tags.

#### 3. **Stop an Instance**

```python
ec2_client.stop_instances(InstanceIds=['i-1234567890abcdef0'])
print("Instance stop initiated (may take a few seconds)")
```

**Important:** This is destructive. Only use it in Phase 1 when you've added protection logic.

### CloudWatch Client: Getting Metrics

CloudWatch stores metrics like CPU usage. This is how you check if an instance is idle.

#### **Get CPU Metric Data**

```python
import boto3
from datetime import datetime, timedelta

cloudwatch_client = boto3.client('cloudwatch', region_name='us-east-1')

instance_id = 'i-1234567890abcdef0'

# Calculate date range (last 7 days)
end_time = datetime.utcnow()
start_time = end_time - timedelta(days=7)

# Fetch metric data
response = cloudwatch_client.get_metric_statistics(
    Namespace='AWS/EC2',
    MetricName='CPUUtilization',
    Dimensions=[
        {
            'Name': 'InstanceId',
            'Value': instance_id
        }
    ],
    StartTime=start_time,
    EndTime=end_time,
    Period=3600,  # 1 hour
    Statistics=['Maximum']  # Get max CPU per hour
)

# Find the maximum CPU value
datapoints = response['Datapoints']
if datapoints:
    max_cpu = max(point['Maximum'] for point in datapoints)
    print(f"Max CPU in last 7 days: {max_cpu}%")
else:
    print("No metric data available (instance is too new or has no CPU data)")
```

**For your project:**
- If `max_cpu < 2.0`, the instance is idle (a "zombie").
- If there's no metric data, assume it's a new instance and skip it.

### SNS Client: Send Notifications

```python
sns_client = boto3.client('sns', region_name='us-east-1')

topic_arn = 'arn:aws:sns:us-east-1:123456789012:my-topic'

sns_client.publish(
    TopicArn=topic_arn,
    Subject='Cloud Janitor Report',
    Message='Found 3 idle instances:\n- i-123\n- i-456\n- i-789'
)
```

**For your project:** Phase 2 will use this to send Slack or email reports.

### S3 Client: Read Configuration

```python
s3_client = boto3.client('s3', region_name='us-east-1')

# Read a config file from S3
response = s3_client.get_object(
    Bucket='my-bucket',
    Key='config.json'
)

import json
config = json.loads(response['Body'].read().decode('utf-8'))
print(config['mode'])  # 'dry-run' or 'action'
```

**For your project:** Phase 2 will use this to load rules from S3.

---

## Part 3: Error Handling & Best Practices

### Handle Missing Metric Data Gracefully

```python
try:
    response = cloudwatch_client.get_metric_statistics(...)
    datapoints = response['Datapoints']
    
    if not datapoints:
        print(f"No data for {instance_id} - skipping")
        return None
    
    max_cpu = max(point['Maximum'] for point in datapoints)
    return max_cpu
except Exception as e:
    print(f"Error fetching metrics: {e}")
    return None
```

### Handle Missing Tags

```python
tags = {}
if 'Tags' in instance:
    for tag in instance['Tags']:
        tags[tag['Key']] = tag['Value']

# Safe access to tags
env = tags.get('Env', 'Unknown')  # Returns 'Unknown' if 'Env' key doesn't exist
if env == 'Prod':
    return "IGNORE_PROD"
```

### Pagination (For Large Result Sets)

If you have many EC2 instances, AWS returns paginated results:

```python
ec2_client = boto3.client('ec2', region_name='us-east-1')

paginator = ec2_client.get_paginator('describe_instances')

for page in paginator.paginate():
    for reservation in page['Reservations']:
        for instance in reservation['Instances']:
            print(instance['InstanceId'])
```

**For your project:** Use this when you expand beyond a few instances.

---

## Part 4: Phase 0 Implementation Pattern

Here's the skeleton for your Phase 0 code:

```python
import boto3
from datetime import datetime, timedelta

def lambda_handler(event, context):
    ec2 = boto3.client('ec2', region_name='us-east-1')
    cloudwatch = boto3.client('cloudwatch', region_name='us-east-1')
    
    zombies = []
    
    # Step 1: Get all running Test instances
    response = ec2.describe_instances(
        Filters=[
            {'Name': 'instance-state-name', 'Values': ['running']},
            {'Name': 'tag:Env', 'Values': ['Test']}
        ]
    )
    
    # Step 2: Check each instance for idleness
    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            instance_id = instance['InstanceId']
            
            # Get tags
            tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}
            
            # Skip protected instances
            if tags.get('Protected') == 'True':
                continue
            
            # Get CPU metrics
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(days=7)
            
            metrics = cloudwatch.get_metric_statistics(
                Namespace='AWS/EC2',
                MetricName='CPUUtilization',
                Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
                StartTime=start_time,
                EndTime=end_time,
                Period=3600,
                Statistics=['Maximum']
            )
            
            # Determine if zombie
            if metrics['Datapoints']:
                max_cpu = max(point['Maximum'] for point in metrics['Datapoints'])
                if max_cpu < 2.0:
                    zombies.append(instance_id)
                    print(f"ZOMBIE: {instance_id} (max CPU: {max_cpu}%)")
    
    # Step 3: Report
    print(f"\nTotal zombies found: {len(zombies)}")
    return {'statusCode': 200, 'zombies': zombies}
```

---

## Part 5: Testing Locally

You *can* test Boto3 code locally if you have AWS credentials configured:

```bash
# Set up AWS credentials (AWS CLI)
aws configure

# Then test your Python script locally
python my_janitor.py
```

**For production:** Deploy to Lambda where the IAM Role handles permissions automatically.

---

## Summary Cheat Sheet

| Task | Code |
|------|------|
| Create EC2 client | `ec2 = boto3.client('ec2', region_name='us-east-1')` |
| Get running Test instances | `ec2.describe_instances(Filters=[{'Name': 'instance-state-name', 'Values': ['running']}, {'Name': 'tag:Env', 'Values': ['Test']}])` |
| Get CPU metrics (7 days) | `cloudwatch.get_metric_statistics(Namespace='AWS/EC2', MetricName='CPUUtilization', ..., Period=3600, Statistics=['Maximum'])` |
| Stop an instance | `ec2.stop_instances(InstanceIds=['i-xxx'])` |
| Get tags from instance | `tags = {tag['Key']: tag['Value'] for tag in instance.get('Tags', [])}` |
| Send SNS notification | `sns.publish(TopicArn=arn, Subject='...', Message='...')` |
| Read S3 config | `s3.get_object(Bucket='...', Key='...'); json.loads(response['Body'].read())` |

---

## Next Steps

1. **Understand the structure:** Read through the EC2 and CloudWatch patterns above.
2. **Build Phase 0:** Use the skeleton code to write your finder/analyzer.
3. **Deploy to Lambda:** Copy your code into a Lambda function, attach an IAM role with the necessary permissions.
4. **Test manually:** Trigger the Lambda from the AWS console and check CloudWatch logs.
5. **Move to Phase 1:** Add the stop logic and EventBridge scheduler.

You now have enough knowledge to build the Cloud Janitor without drowning in AWS documentation.