import time
from helper import Helper
import sys

def upgrade(args):
    h = Helper()
    if args[2]:
        conf_file = args[3]
        valid = h.parse_and_validate(conf_file,
                                     ['project_id', 'cf_url', 'cf_stack_name', 'instance_type', 'key_pair_name', 'vpc_id',
                                      'subnet_id', 'region', 'whitelist', 'private'])
        if not valid:
            return False
        project_id, cf_url, cf_stack_name, instance_type, key_pair_name, vpc_id, subnet_id, region, whitelist, private = valid
        host, instance_id = h.deploy_dremio(cf_stack_name, cf_url, instance_type, key_pair_name, vpc_id, subnet_id,
                                            region, whitelist, private)
    else:
        valid = h.parse_and_validate(conf_file,
                                     ['project_id', 'instance_type', 'key_pair_name', 'vpc_id',
                                      'subnet_id', 'region', 'private', 'ami', 'iam_instance_profile_arn', 'iam_instance_profile'])
        if not valid:
            return False
        project_id, instance_type, key_pair_name, vpc_id, subnet_id, region, whitelist, private, ami = valid
        host, instance_id = h.deploy_coordinator(instance_type, key_pair_name, vpc_id, subnet_id, region, whitelist,
                                                 private, ami)
    h.stop_dremio_project(host, proj_id=project_id, instance=instance_id)
    time.sleep(240)  # sleep for 4 minutes
    h.open_dremio_project(host, proj_id=project_id, instance=instance_id)

if __name__ == "__main__":
    # check the action
    if sys.argv[1] == "upgrade":
        upgrade(sys.argv)
    elif sys.argv[1] == "deploy":
        pass

