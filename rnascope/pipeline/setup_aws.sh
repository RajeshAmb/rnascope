#!/bin/bash
# ============================================================================
# One-time AWS infrastructure setup for RNAscope real pipeline
# Run this once to create: ECR repo, Batch compute env, job queue, job def
# ============================================================================

set -e
REGION="us-east-2"
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO="rnascope-worker"
ECR_URI="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com/${ECR_REPO}"

echo "=== Setting up RNAscope pipeline infrastructure ==="
echo "Account: $ACCOUNT"
echo "Region: $REGION"

# 1. Create ECR repository
echo "Creating ECR repository..."
aws ecr create-repository --repository-name $ECR_REPO --region $REGION 2>/dev/null || echo "ECR repo already exists"

# 2. Build and push Docker image
echo "Building Docker image..."
cd "$(dirname "$0")/../.."
docker build -f rnascope/pipeline/Dockerfile.worker -t $ECR_REPO .
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ECR_URI
docker tag $ECR_REPO:latest $ECR_URI:latest
docker push $ECR_URI:latest
echo "Image pushed to $ECR_URI:latest"

# 3. Create IAM role for Batch jobs
echo "Creating Batch execution role..."
cat > /tmp/batch-trust-policy.json << 'TRUST'
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "ecs-tasks.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}
TRUST

aws iam create-role \
  --role-name rnascope-batch-role \
  --assume-role-policy-document file:///tmp/batch-trust-policy.json \
  2>/dev/null || echo "Role already exists"

aws iam attach-role-policy --role-name rnascope-batch-role \
  --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess
aws iam attach-role-policy --role-name rnascope-batch-role \
  --policy-arn arn:aws:iam::aws:policy/CloudWatchLogsFullAccess

ROLE_ARN="arn:aws:iam::${ACCOUNT}:role/rnascope-batch-role"

# 4. Create Batch compute environment (Spot for cost savings)
echo "Creating Batch compute environment..."
aws batch create-compute-environment \
  --compute-environment-name rnascope-compute-env \
  --type MANAGED \
  --compute-resources "{
    \"type\": \"SPOT\",
    \"bidPercentage\": 70,
    \"minvCpus\": 0,
    \"maxvCpus\": 16,
    \"desiredvCpus\": 0,
    \"instanceTypes\": [\"r6i.xlarge\", \"r6i.2xlarge\", \"r5.xlarge\"],
    \"subnets\": [\"subnet-default\"],
    \"securityGroupIds\": [\"sg-default\"],
    \"instanceRole\": \"ecsInstanceRole\",
    \"spotIamFleetRole\": \"arn:aws:iam::${ACCOUNT}:role/aws-ec2-spot-fleet-tagging-role\"
  }" \
  --region $REGION 2>/dev/null || echo "Compute env already exists"

# 5. Create job queue
echo "Creating Batch job queue..."
aws batch create-job-queue \
  --job-queue-name rnascope-queue \
  --priority 1 \
  --compute-environment-order "order=1,computeEnvironment=rnascope-compute-env" \
  --region $REGION 2>/dev/null || echo "Job queue already exists"

# 6. Create job definition
echo "Creating Batch job definition..."
aws batch register-job-definition \
  --job-definition-name rnascope-job-def \
  --type container \
  --container-properties "{
    \"image\": \"${ECR_URI}:latest\",
    \"vcpus\": 4,
    \"memory\": 30000,
    \"jobRoleArn\": \"${ROLE_ARN}\",
    \"executionRoleArn\": \"${ROLE_ARN}\"
  }" \
  --region $REGION

# 7. Download and build Salmon index for cotton_arboreum
echo "Building Salmon index for cotton_arboreum..."
REFS_DIR="/tmp/rnascope_refs"
mkdir -p $REFS_DIR
cd $REFS_DIR

echo "Downloading G. arboreum transcriptome from Ensembl Plants..."
wget -q "https://ftp.ensemblgenomes.org/pub/plants/release-57/fasta/gossypium_arboreum/cdna/Gossypium_arboreum.Cotton_A_CRI_v1.cdna.all.fa.gz" \
  -O ga_transcriptome.fa.gz 2>/dev/null || echo "Download may have failed — check URL"

if [ -f ga_transcriptome.fa.gz ]; then
  echo "Building Salmon index (this takes ~10 min)..."
  salmon index -t ga_transcriptome.fa.gz -i ga_salmon_index -k 31 --threads 4

  echo "Uploading Salmon index to S3..."
  aws s3 sync ga_salmon_index/ s3://rnascope-references/salmon-index/cotton_arboreum/ --region $REGION
  echo "Salmon index uploaded!"
else
  echo "WARNING: Transcriptome download failed. Build index manually."
fi

echo ""
echo "=== Setup complete! ==="
echo "ECR Image: $ECR_URI:latest"
echo "Batch Queue: rnascope-queue"
echo "Batch Job Def: rnascope-job-def"
echo ""
echo "Add to Render env vars:"
echo "  ECR_IMAGE_URI=$ECR_URI:latest"
echo "  BATCH_JOB_QUEUE=rnascope-queue"
echo "  BATCH_JOB_DEFINITION=rnascope-job-def"
