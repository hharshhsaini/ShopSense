#!/usr/bin/env bash
# Deploy the MCP server to one EC2 instance running Docker.
#
#   REGION=ap-south-1 RUNNER_CIDR=203.0.113.7/32 deploy/ec2_deploy.sh up      # create + deploy
#   deploy/ec2_deploy.sh push                                                 # redeploy code/index
#   deploy/ec2_deploy.sh status | logs | down
#
# Creates (tagged shopsense-mcp): a key pair (private key kept in deploy/, git-ignored),
# a security group (SSH from this machine's IP, port 8000 from RUNNER_CIDR), an
# Elastic IP and an arm64 instance. Credentials come from the normal AWS CLI chain;
# nothing secret is written into the image or the repository.
set -euo pipefail
cd "$(dirname "$0")/.."

STATE=deploy/state.env
[ -f "$STATE" ] && source "$STATE"
REGION=${REGION:-ap-south-1}
INSTANCE_TYPE=${INSTANCE_TYPE:-c7g.large}
RUNNER_CIDR=${RUNNER_CIDR:-0.0.0.0/0}
NAME=shopsense-mcp
KEY=deploy/$NAME.pem
AWS="aws --region $REGION --output text"
SSH_OPTS="-i $KEY -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10"

save() { printf 'REGION=%s\nINSTANCE_TYPE=%s\nRUNNER_CIDR=%s\nINSTANCE_ID=%s\nSG_ID=%s\nALLOC_ID=%s\nPUBLIC_IP=%s\n' \
  "$REGION" "$INSTANCE_TYPE" "$RUNNER_CIDR" "${INSTANCE_ID:-}" "${SG_ID:-}" "${ALLOC_ID:-}" "${PUBLIC_IP:-}" > "$STATE"; }

up() {
  [ -f index/meta.json ] || { echo 'Build the semantic index first: python build_index.py'; exit 1; }
  if [ ! -f "$KEY" ]; then
    $AWS ec2 create-key-pair --key-name $NAME --key-type ed25519 --query KeyMaterial > "$KEY"
    chmod 600 "$KEY"
  fi
  MY_IP=$(curl -fsS https://checkip.amazonaws.com)
  if [ -z "${SG_ID:-}" ]; then
    VPC=$($AWS ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId')
    SG_ID=$($AWS ec2 create-security-group --group-name $NAME --description 'ShopSense MCP server' \
      --vpc-id "$VPC" --query GroupId)
    $AWS ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 22 --cidr "$MY_IP/32" >/dev/null
    $AWS ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 8000 --cidr "$RUNNER_CIDR" >/dev/null
    save
  fi
  if [ -z "${INSTANCE_ID:-}" ]; then
    AMI=$($AWS ssm get-parameter --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64 \
      --query Parameter.Value)
    # Not every zone offers every instance type: use a default subnet in one that does.
    AZ=$($AWS ec2 describe-instance-type-offerings --location-type availability-zone \
      --filters Name=instance-type,Values="$INSTANCE_TYPE" --query 'InstanceTypeOfferings[].Location' | tr '\t' '\n' | sort | head -1)
    SUBNET=$($AWS ec2 describe-subnets --filters Name=default-for-az,Values=true Name=availability-zone,Values="$AZ" \
      --query 'Subnets[0].SubnetId')
    INSTANCE_ID=$($AWS ec2 run-instances --image-id "$AMI" --instance-type "$INSTANCE_TYPE" --key-name $NAME \
      --subnet-id "$SUBNET" --security-group-ids "$SG_ID" --metadata-options HttpTokens=required \
      --block-device-mappings 'DeviceName=/dev/xvda,Ebs={VolumeSize=20,VolumeType=gp3}' \
      --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NAME}]" \
      --user-data '#!/bin/bash
dnf install -y docker rsync && systemctl enable --now docker && usermod -aG docker ec2-user' \
      --query 'Instances[0].InstanceId')
    save
    $AWS ec2 wait instance-running --instance-ids "$INSTANCE_ID"
  fi
  if [ -z "${PUBLIC_IP:-}" ]; then
    # Prefer an Elastic IP (survives stop/start); if the account's quota is used up, keep the
    # instance's own public IP, which stays the same across reboots but changes on stop/start.
    if ALLOC_ID=$($AWS ec2 allocate-address --domain vpc --query AllocationId 2>/dev/null); then
      $AWS ec2 associate-address --instance-id "$INSTANCE_ID" --allocation-id "$ALLOC_ID" >/dev/null
      PUBLIC_IP=$($AWS ec2 describe-addresses --allocation-ids "$ALLOC_ID" --query 'Addresses[0].PublicIp')
    else
      ALLOC_ID=
      echo 'No Elastic IP available (quota); using the instance public IP. Do not stop the instance.'
      PUBLIC_IP=$($AWS ec2 describe-instances --instance-ids "$INSTANCE_ID" \
        --query 'Reservations[0].Instances[0].PublicIpAddress')
    fi
    save
  fi
  echo "Waiting for SSH and Docker on $PUBLIC_IP ..."
  for _ in $(seq 60); do
    ssh $SSH_OPTS ec2-user@"$PUBLIC_IP" 'command -v docker && command -v rsync' >/dev/null 2>&1 && break
    sleep 5
  done
  push
}

push() {
  rsync -az --delete -e "ssh $SSH_OPTS" --exclude .git --exclude .venv --exclude '__pycache__' \
    --exclude 'deploy/*.pem' --exclude deploy/state.env ./ ec2-user@"$PUBLIC_IP":app/
  ssh $SSH_OPTS ec2-user@"$PUBLIC_IP" "cd app && sudo docker build -q -t shopsense . && \
    (sudo docker rm -f shopsense >/dev/null 2>&1 || true) && \
    sudo docker run -d --name shopsense --restart unless-stopped -p 8000:8000 \
      -e MCP_ALLOWED_HOSTS='localhost:*,127.0.0.1:*,[::1]:*,$PUBLIC_IP:*,$PUBLIC_IP' shopsense"
  echo "Waiting for readiness ..."
  for _ in $(seq 60); do
    curl -fsS "http://$PUBLIC_IP:8000/healthz" 2>/dev/null && { echo; echo "MCP endpoint: http://$PUBLIC_IP:8000/mcp"; return; }
    sleep 5
  done
  echo 'Server did not become ready; check: deploy/ec2_deploy.sh logs'; exit 1
}

status() { echo "instance=$INSTANCE_ID ip=$PUBLIC_IP"; curl -fsS "http://$PUBLIC_IP:8000/healthz"; echo; }
logs() { ssh $SSH_OPTS ec2-user@"$PUBLIC_IP" 'sudo docker logs --tail 100 shopsense'; }

down() {
  [ -n "${ALLOC_ID:-}" ] && { $AWS ec2 disassociate-address --public-ip "$PUBLIC_IP" >/dev/null 2>&1 || true
    $AWS ec2 release-address --allocation-id "$ALLOC_ID" || true; }
  [ -n "${INSTANCE_ID:-}" ] && { $AWS ec2 terminate-instances --instance-ids "$INSTANCE_ID" >/dev/null
    $AWS ec2 wait instance-terminated --instance-ids "$INSTANCE_ID"; }
  [ -n "${SG_ID:-}" ] && $AWS ec2 delete-security-group --group-id "$SG_ID" || true
  $AWS ec2 delete-key-pair --key-name $NAME || true
  rm -f "$STATE" "$KEY"
  echo 'All shopsense-mcp resources removed.'
}

"${1:-status}"
