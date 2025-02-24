import requests
import boto3
import json
from datetime import datetime
import time
import configparser

ACTION_URL = "http://{0}/project/{1}/action"
STATUS_URL = "http://{0}/aws/gateway/progress/{1}?instanceId={2}"
AUTH_URL = "http://{0}/aws/gateway/validateId"
GET_ENGINES = "http://{0}:9047/apiv2/provision/clusters"
CREATE_PROJECT_URL = "http://{0}:9047/aws/gateway/projectInput?instanceId={1}"
CREATE_CUSTOM_PROJECT_URL = "http://{0}:9047/aws/gateway/customProject/?instanceId={1}"
CUSTOM_PROJECT_STATUS_URL = "http://{0}:9047/aws/gateway/progress/{1}?instanceId={2}"
DREMIO_AUTH_TYPE_CMD = "awk -F'\"' '/auth.type:/ {print $2}' /opt/dremio/conf/dremio.conf"


class Helper:
    def __init__(self):
        self.session = None
        self.conf = None

    def parse_and_validate(self, config_file, required):
        self.conf = configparser.ConfigParser()
        self.conf.read(config_file)
        # validate mandatory properties are provided
        missing = set(required) - set(self.conf['default'].keys())
        if len(missing) > 0:
            print("Missing mandatory parameters: {0}".format(missing))
            return False
        else:
            self.conf = self.conf['default']
            return True

    def __get(self, url):
        try:
            if self.conf['pat']:
                d = {
                    'Authorization': f'Bearer {self.conf["pat"]}',
                    'Accept': 'application/json',
                    'Content-Type': 'application/json'
                }
                res = requests.request("GET", url, headers=d)
            else:
                res = requests.request("GET", url)
            if res.status_code == 200:
                ret = res.json()
            else:
                ret = False
        except Exception as e:
            print(e)
        else:
            return ret

    def __post(self, url, d, auth=False):
        try:
            payload = json.dumps(d)
            if auth:
                headers = {
                    'Authorization': f'Bearer {self.conf["pat"]}',
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                }
            else:
                headers = {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                }
            res = requests.request("POST", url, headers=headers, data=payload)
            if res.status_code == 200:
                ret = res.json()
            else:
                ret = False
        except Exception as e:
            print(e)
        else:
            return ret

    def json_serial(self, obj):
        """JSON serializer for objects not serializable by default json code"""
        if isinstance(obj, datetime):
            serial = obj.isoformat()
            return serial
        raise TypeError("Type not serializable")

    def get_boto3_session(self):
        if (self.session is None):
            self.session = boto3.Session(region_name=self.conf['region'],
                                         aws_access_key_id=self.conf['access'],
                                         aws_secret_access_key=self.conf['secret'])
            if self.conf['role_arn']:
                sts_client = self.session.client('sts')
                assumed_role_response = sts_client.assume_role(
                    RoleArn=self.conf['role_arn'],
                    RoleSessionName='AJF-TEST-XACCROLE'  # Give your session a descriptive name
                )
                self.session = boto3.Session(
                    aws_access_key_id=assumed_role_response['Credentials']['AccessKeyId'],
                    aws_secret_access_key=assumed_role_response['Credentials']['SecretAccessKey'],
                    aws_session_token=assumed_role_response['Credentials']['SessionToken'],
                    region_name=self.conf['region']
                )
        return self.session

    def deploy_dremio(self, stack_name, CF_URL, instance_type, key_pair_name, vpc_id, subnet_id, region, whitelist,
                      private=False):
        try:
            client = boto3.client('cloudformation', region_name=region)
            res = client.create_stack(
                StackName=stack_name,
                TemplateURL=CF_URL,
                Capabilities=['CAPABILITY_IAM'],
                Parameters=[
                    {
                        'ParameterKey': 'DremioGatewayEC2InstanceType',
                        'ParameterValue': instance_type
                    },
                    {
                        'ParameterKey': 'DremioGatewayEC2KeyPair',
                        'ParameterValue': key_pair_name
                    },
                    {
                        'ParameterKey': 'DremioGatewayEC2VPC',
                        'ParameterValue': vpc_id
                    },
                    {
                        'ParameterKey': 'DremioGatewayEC2Subnet',
                        'ParameterValue': subnet_id
                    },
                    {
                        'ParameterKey': 'DremioGatewayEC2IPWhitelist',
                        'ParameterValue': whitelist
                    },
                    {
                        'ParameterKey': 'DremioGatewayEC2InstanceProfile',
                        'ParameterValue': ''
                    },
                    {
                        'ParameterKey': 'DremioGatewayEC2SecurityGroup',
                        'ParameterValue': ''
                    }
                ]
            )
            waiter = client.get_waiter('stack_create_complete')
            waiter.wait(StackName=stack_name)
        except Exception as e:
            raise
        else:
            stack = client.describe_stacks(StackName=res['StackId'])
            print(json.dumps(
                stack,
                indent=2,
                default=self.json_serial
            ))
            outputs = stack['Stacks'][0]['Outputs']
            # sort list by OutputKey
            outputs.sort(key=lambda attr: attr['OutputKey'])
            if private:
                init_url = outputs[0]['OutputValue']
                tmp = init_url.split("/")
                host = tmp[2]
                instance_id = tmp[3].split("=")[1]
            else:
                init_url = outputs[1]['OutputValue']
                tmp = init_url.split("/")
                host = tmp[2]
                instance_id = tmp[3].split("=")[1]
            # check deployment active
            while (True):
                res = self.__get(init_url)
                if res:
                    break
                time.sleep(100)
            print("Dremio deployment is active")
            return [host, instance_id, init_url]

    def deploy_coordinator(self, instance_type, key_pair_name, vpc_id, subnet_id, region, whitelist,
                           private, ami, iam_instance_profile_arn, iam_instance_profile):
        try:
            client = boto3.client('ec2', region_name=region)
            resp = client.create_instances(
                ImageId=ami,
                SubnetId=subnet_id,
                MinCount=1,
                MaxCount=1,
                InstanceType=instance_type,
                IamInstanceProfile={
                    'Arn': iam_instance_profile_arn,
                    'Name': iam_instance_profile
                },
                KeyName=key_pair_name,
                BlockDeviceMappings=[
                    {
                        'DeviceName': '/dev/xvda',
                        'Ebs': {
                            'SnapshotId': 'dremio-coordinator',
                            'VolumeSize': 50,
                            'VolumeType': 'standard'
                        }
                    },
                ],
            )
            if len(resp) > 0:
                # successfully created
                if private:
                    host = resp[0]['private_ip_address']
                else:
                    host = resp[0]['public_ip_address']
                instance_id = resp[0]['id']
                ret = [host, instance_id]
            else:
                # failed
                ret = False
        except Exception as e:
            print(e)
            return False
        else:
            ret

    def open_dremio_project(self, host, proj_id, instance):
        url = "http://{0}/aws/gateway/project/{1}/action".format(host, proj_id)
        payload = json.dumps({
            "action": "START",
            "id": proj_id,
            "instanceId": instance
        })
        res = self.__post(url, payload)
        if res:
            return True
        else:
            return False

    def stop_dremio_project(self, host, proj_id, instance):
        url = "http://{0}/aws/gateway/project/{1}/action".format(host, proj_id)
        payload = json.dumps({
            "action": "STOP",
            "id": proj_id,
            "instanceId": instance
        })
        res = self.__post(url, payload)
        if res:
            return True
        else:
            return False

    def create_project(self, host, instance_id):
        url = CREATE_PROJECT_URL.format(host, instance_id)
        resp = self.__get()
        if resp:
            return resp
        else:
            return False

    def create_s3_bucket(bucket_name, proj_id, region):
        client = boto3.client('s3', region_name=region)
        resp = client.create_bucket(
            Bucket=bucket_name
        )
        # create tags
        client.put_bucket_tagging(
            Bucket=bucket_name,
            Tagging={
                'TagSet': [
                    {
                        'Key': "dremio_managed",
                        'Value': "true"
                    },
                    {
                        'Key': "dremio_project_id",
                        'Value': proj_id
                    }
                ]
            }
        )

    def create_ebs(self, proj_name, proj_id, region, encrypted=False):
        client = boto3.client('ec2', region_name=region)
        resp = client.create_volume(
            Size=100,
            VolumeType='gp2',
            Encrypted=encrypted,
            TagSpecifications=[
                {
                    'ResourceType': 'volume',
                    'Tags': [
                        {
                            'Key': 'dremio_managed',
                            'Value': 'true'
                        },
                        {
                            'Key': 'dremio_project_id',
                            'Value': proj_id
                        },
                        {
                            'Key': 'dremio_project_name',
                            'Value': proj_name
                        },
                        {
                            'Key': 'dremio_project_pending',
                            'Value': 'true'
                        }
                    ]
                }
            ]
        )
        return resp['VolumeId']

    def create_efs(self, proj_id, region):
        client = boto3.client('efs', region_name=region)
        resp = client.create_file_system(
            PerformanceMode="generalPurpose",
            Tags=[
                {
                    'Key': 'dremio_managed',
                    'Value': 'true'
                },
                {
                    'Key': 'dremio_project_id',
                    'Value': proj_id
                }
            ]
        )
        return resp['FileSystemId']

    def check_project_status(self, host, instance_id):
        for i in range(0, 20):
            url = CUSTOM_PROJECT_STATUS_URL.format(host, i, instance_id)
            resp = self.__get(url)
            if resp:
                # get the last element
                last = resp['data'][-1:]
                if len(last) > 0:
                    if last['isFinal'] == "true" and last['isSuccess'] == "true":
                        return True
                    elif last['isFinal'] == "true" and last['isSuccess'] == "false":
                        return last['error']

    def create_custom_project(self, host, proj_name, proj_id, instance_id, ebs_id, efs_id, bucket_name):
        res = self.create_project(host, instance_id)
        if not res:
            return False
        d = {
            "name": proj_name,
            "id": res['id'],
            "engineSize": "SMALL",
            "customNodeCount": 0,
            "enableAutoBackups": "false",
            "engineNodeType": "STANDARD",
            "iamInstanceProfile": "",
            "instanceId": instance_id,
            "disablePublicIp": "true",
            "ebsVolumeId": ebs_id,
            "efsVolumeName": efs_id,
            "s3BucketName": bucket_name
        }
        url = CREATE_CUSTOM_PROJECT_URL.format(host, instance_id)
        res = self.__post(url, d)
        if res['statusCode'] != 200:
            return False
        else:
            # check project
            res = self.check_project_status(host, instance_id)
            if res == True:
                print("Project was created successfully")
            else:
                print("Project failed to create: {0}".format(res))

    def search_tags(self, tags, criteria):
        """
            Helper function to search for a specific tag key in a list of tags.

            Args:
                tags (list): A list of tag dictionaries (e.g., [{'Key': 'Name', 'Value': 'MyInstance'}, ...]).
                criteria (str): The tag key to search for.

            Returns:
                str: The value of the tag if found, or None if not found.
            """
        found = False
        for tag in tags:
            if tag['Key'] == criteria:
                found = True
        return found

    # find coordinator
    def find_coordinator(self):
        """
        Finds a Dremio coordinator instance in a given AWS region.

        Args:
            region (str): The AWS region to search in.

        Returns:
            dict: A dictionary containing the EC2 instance details of the coordinator,
                  or None if no coordinator is found.
        """
        try:
            session = self.get_boto3_session()
            ec2 = session.client('ec2')

            filters = [{
                'Name': 'vpc-id',
                'Values': [self.conf['vpc_id']]
            }, {
                'Name': 'subnet-id',
                'Values': [self.conf['subnet_id']]
            }, {
                'Name': 'tag:dremio_managed',
                'Values': ['true']
            }, {
                'Name': 'instance-state-name',
                'Values': ['running']
            }]

            response = ec2.describe_instances(Filters=filters)

            for reservation in response['Reservations']:
                for instance in reservation['Instances']:
                    # Check if the instance does NOT have the dremio_role tag
                    if not self.search_tags(instance['Tags'], 'dremio_role'):  # Use the helper function
                        print("Found a Dremio coordinator node")
                        return instance

            return None  # No coordinator found

        except Exception as e:
            print(f"Error finding coordinator: {e}")
            return None

    def execute_command_on_ec2(self, commands, instance_id):
        session = self.get_boto3_session()
        client = session.client('ssm')
        send_resp = client.send_command(
            DocumentName="AWS-RunShellScript",  # One of AWS' preconfigured documents
            Parameters={'commands': commands},
            InstanceIds=[instance_id],
        )
        time.sleep(1)
        # get response
        resp = client.get_command_invocation(
            CommandId=send_resp['Command']['CommandId'],
            InstanceId=send_resp['Command']['InstanceIds'][0]
        )
        return resp

    def get_authentication_method(self, coordinator_id):
        cmd = [DREMIO_AUTH_TYPE_CMD]
        res = self.execute_command_on_ec2(cmd, coordinator_id)
        if res:
            return res['StandardOutputContent'].replace("\n", "")

    def get_engines(self, coordinator):
        d = []
        res = self.__get(GET_ENGINES.format(coordinator))
        if res:
            # loop through the engines
            for cluster in res['clusterList']:
                d.append(
                    {
                        "name": cluster['name'],
                        "instanceType": cluster['awsProps']['instanceType'],
                        "size": cluster['dynamicConfig']['containerCount'],
                        "shutdownInterval":  cluster['shutdownInterval']

                    })
        return d