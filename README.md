Dremio AWS Edition Client
====
This unofficial script is for managing your AWS Edition environment. It enables administrators to deploy and upgrade their environment seemlessly without the need to interfact with the Dremio projects UI.

The key features of this tool are:
- **AWS Edition Deployment**: This will deploy a fully functional Dremio environment inside your AWS Account.
- **AWS Edition Upgrade**: This will upgrade an existing project inside your AWS Account.

## Pre-requisite
Before we can use the script we will need to ensure the following:

- The user executing this script has the ability to deploy the required AWS resources for Dremio, these include S3, EBS and EFS.
- You have a python3 environment that has the dependencies inside requirements.txt installed

This script can be used to upgrade your Dremio environment using two approaches (1) Cloudformation or (2) AMI. Based on the approach that you choose you will need to provide a number of properties that are required by the script. Below is a table of the properties and their requirements.

| Variable  	| Description  | Required 	|
|---	|:---	|	---|
| project_id 	| Project ID that you want to Upgrade 	| Yes 	|
| cf_url 	| Cloudformation script URL	| Yes for Cloudformation Deployment or Upgrades 	|
| cf_stack_name 	|  Stack Name for Cloudformation deployments or upgrades 	| Yes for Cloudformation Deployment or Upgrades 	|
| instance_type 	| EC2 instance type for the coordinator node 	| Yes 	|
| key_pair_name 	| Key pair to attach to the coordinator instance 	| Yes 	|
| vpc_id 	| VPC to deploy the environment within 	| Yes for Cloudformation Deployment or Upgrades 	|
| subnet_id 	| Subnet to deploy Dremio within 	| Yes 	|
| region 	| AWS Region for the deployment 	| Yes 	|
| whitelist 	| IP range to whitelist for Dremio access | Yes for Cloudformation Deployment or Upgrades |
| private 	| Flag to determine if the deployment should be public or private 	| No, default value is public |
| custom_ami 	| AMI to use for Dremio coordinator 	| No, only for upgrades using a specific AMI |

If you are using approach (1) then you can simply execute `python3 aws-edition-client.py upgrade true dremio-upgrade.conf`, if you are using approach (2) then you can simply execute `python3 aws-edition-client.py upgrade false dremio-upgrade.conf`.

