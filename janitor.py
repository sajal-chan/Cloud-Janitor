import boto3
from datetime import datetime, timedelta

# --- CONFIGURATION ---
TARGET_TAG_KEY = 'Env'
TARGET_TAG_VALUE = 'Test'
MAX_CPU_THRESHOLD = 2.0  # If CPU < 2%, it's a zombie
DAYS_TO_LOOK_BACK = 7

# --- AWS CLIENTS ---
# We need two clients: EC2 (to find servers) and CloudWatch (to check stats)
ec2 = boto3.client('ec2')
cloudwatch = boto3.client('cloudwatch')

def get_test_instances():
    """
    Finds all running EC2 instances that match our tag.
    """
    print(f"🔍 Scanning for instances with tag {TARGET_TAG_KEY}={TARGET_TAG_VALUE}...")
    
    response = ec2.describe_instances(
        Filters=[
            {'Name': f'tag:{TARGET_TAG_KEY}', 'Values': [TARGET_TAG_VALUE]},
            {'Name': 'instance-state-name', 'Values': ['running']}
        ]
    )
    
    instances = []
    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            instances.append(instance['InstanceId'])
            
    print(f"Found {len(instances)} candidates.")
    return instances

def get_max_cpu(instance_id):
    """
    Asks CloudWatch: "What was the highest CPU spike this server had in the last week?"
    """
    # Define the time window (Last 7 days)
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(days=DAYS_TO_LOOK_BACK)

    try:
        response = cloudwatch.get_metric_statistics(
            Namespace='AWS/EC2',
            MetricName='CPUUtilization',
            Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
            StartTime=start_time,
            EndTime=end_time,
            Period=86400 * DAYS_TO_LOOK_BACK, # Look at the whole chunk as one period
            Statistics=['Maximum']
        )
        
        # If we have data, return the max CPU
        if response['Datapoints']:
            return response['Datapoints'][0]['Maximum']
        else:
            return 0.0 # No data usually means it's brand new or dead
            
    except Exception as e:
        print(f"Error fetching metrics for {instance_id}: {e}")
        return -1

def main():
    # 1. Get the list of instances
    candidates = get_test_instances()
    
    # 2. Check each one
    print("\n--- ANALYZING INSTANCES ---")
    for instance_id in candidates:
        max_cpu = get_max_cpu(instance_id)
        
        print(f"Instance: {instance_id} | Max CPU (7 days): {max_cpu}%")
        
        # 3. Apply the 'Zombie' Logic
        if max_cpu < MAX_CPU_THRESHOLD:
            print(f"❌ ZOMBIE DETECTED! (This instance is wasting money)")
            # In Phase 1, we will add: ec2.stop_instances(...)
        else:
            print(f"✅ Active. (This instance is being used)")
            
    print("\n--- SCAN COMPLETE ---")

if __name__ == "__main__":
    main()
