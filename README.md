# MLflow Setup on Kubernetes

This guide provides step-by-step instructions to deploy MLflow on a Kubernetes cluster with PostgreSQL as the backend store.

## Prerequisites

- AWS Account
- kubectl installed
- Docker installed
- kind (Kubernetes in Docker) installed

## Step 1: Create AWS Infrastructure

### 1.1 Create RDS PostgreSQL Instance

1. Go to AWS RDS Console
2. Click "Create database"
3. Select PostgreSQL as the engine
4. Configure the following:
   - **DB Instance Identifier**: `<your-db-instance-name>`
   - **Master Username**: `<username>`
   - **Master Password**: `<password>`
   - **DB Instance Class**: Choose based on your requirements (e.g., db.t3.micro for testing)
   - **Storage**: Configure as needed
   - **VPC**: Select or create a VPC
   - **Security Group**: Create or select a security group (note this for later)
   - **Public Access**: Yes (if accessing from outside VPC) or No (if only from EC2)
   - **Database Name**: `mlflow`

4. Click "Create database" and wait for it to become available
5. Note the endpoint URL from the RDS console

### 1.2 Create EC2 Instance

1. Go to AWS EC2 Console
2. Click "Launch Instance"
3. Configure the following:
   - **Name**: `<your-ec2-instance-name>`
   - **AMI**: Ubuntu Server or Amazon Linux
   - **Instance Type**: Choose based on your requirements (e.g., t2.micro for testing)
   - **VPC**: **Select the same VPC as your RDS instance**
   - **Security Group**: **Select the same security group as your RDS instance** or ensure they can communicate
   - **Key Pair**: Create or select a key pair for SSH access

4. Click "Launch Instance"

### 1.3 Configure Security Groups

Ensure the security group allows:
- **RDS**: Inbound PostgreSQL traffic (port 5432) from the EC2 security group
- **EC2**: Outbound traffic to RDS on port 5432
- **EC2**: Inbound SSH (port 22) from your IP for management
- **EC2**: Inbound traffic on port 5000 (for MLflow UI access)

## Step 2: Connect to EC2 Instance

SSH into your EC2 instance:

```bash
ssh -i ec2.pem ubuntu@<EC2_PUBLIC_IP>
```

Update the system packages:

```bash
sudo apt update && sudo apt upgrade -y
```

## Step 3: Setup PostgreSQL Database

Install PostgreSQL client:

```bash
sudo apt install -y postgresql-client
```

Connect to the RDS PostgreSQL instance:

```bash
psql "host=<RDS_ENDPOINT> \
port=5432 \
dbname=postgres \
user=<MASTER_USERNAME> \
sslmode=require"
```

Create the MLflow database and user:

```sql
\du

CREATE DATABASE mlflow;
CREATE USER mlflow WITH PASSWORD 'mlflow_password';
GRANT ALL PRIVILEGES ON DATABASE mlflow TO mlflow;

\q
```

## Step 4: Install Docker

Install Docker:

```bash
sudo apt update
sudo apt install -y docker.io
```

Enable and start Docker service:

```bash
sudo systemctl enable docker
sudo systemctl start docker
```

Add user to docker group:

```bash
sudo usermod -aG docker ubuntu
newgrp docker
```

## Step 5: Install kubectl

Download kubectl:

```bash
curl -LO https://dl.k8s.io/release/$(curl -Ls https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl
chmod +x kubectl
sudo mv kubectl /usr/local/bin/
```

Verify installation:

```bash
kubectl version --client
```

## Step 6: Install kind (Kubernetes in Docker)

Download kind:

```bash
curl -Lo kind https://kind.sigs.k8s.io/dl/v0.22.0/kind-linux-amd64
chmod +x kind
sudo mv kind /usr/local/bin/
```

Verify installation:

```bash
kind version
```

## Step 7: Create Kubernetes Cluster

Create the kind cluster:

```bash
kind create cluster --name mlflow --config kind-config.yaml
```

Verify the cluster is running:

```bash
kubectl get nodes
kubectl get pods -A
```

## Step 8: Build and Load MLflow Docker Image

Create directory for MLflow image:

```bash
mkdir mlflow-image
cd mlflow-image
```

Create the Dockerfile (see `mlflow-image/Dockerfile` in this repository).

Build the MLflow Docker image:

```bash
docker build -t mlflow-postgres:1.0 .
```

Verify the image was built:

```bash
docker images | grep mlflow
```

Load the image into the kind cluster:

```bash
kind load docker-image mlflow-postgres:1.0 --name mlflow
```

## Step 9: Deploy MLflow to Kubernetes

Create the MLflow namespace:

```bash
kubectl create namespace mlflow
```

Apply the Kubernetes manifests:

```bash
kubectl apply -f mlflow-db-secret.yaml
kubectl apply -f mlflow-deployment.yaml
kubectl apply -f mlflow-service.yaml
```

## Step 10: Access MLflow UI

Port forward to access MLflow UI:

```bash
kubectl port-forward -n mlflow svc/mlflow 5000:5000 --address=0.0.0.0
```

Access MLflow UI at: `http://<EC2_PUBLIC_IP>:5000`

## Step 11: Setup Python Environment and Run Training

### 11.1 Install Python

Install Python 3 and pip:

```bash
sudo apt install -y python3 python3-pip python3-venv
```

Verify installation:

```bash
python3 --version
pip3 --version
```

### 11.2 Create Virtual Environment

Create a directory for the MLflow client:

```bash
mkdir mlflow-client
cd mlflow-client
```

Create and activate virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

### 11.3 Install Required Packages

Create a `requirements.txt` file:

```txt
mlflow
scikit-learn
```

Install the requirements:

```bash
pip install -r requirements.txt
```

### 11.4 Create Training Script

Create `train.py` (see `mlflow-client/train.py` in this repository).

**Important**: Update the MLflow tracking URI in `train.py`:

```python
mlflow.set_tracking_uri("http://<EC2_PUBLIC_IP>:5000")
```

### 11.5 Run Training

Run the training script:

```bash
python train.py
```

The script will:
- Load the Iris dataset
- Train a Random Forest classifier
- Log parameters, metrics, and model to MLflow
- Display evaluation metrics

Access the MLflow UI at `http://<EC2_PUBLIC_IP>:5000` to view the experiment results.

## Configuration Files

- `kind-config.yaml`: Kind cluster configuration
- `mlflow-db-secret.yaml`: Database connection credentials
- `mlflow-deployment.yaml`: MLflow deployment configuration
- `mlflow-service.yaml`: MLflow service configuration
- `mlflow-image/Dockerfile`: MLflow Docker image definition
- `mlflow-client/train.py`: Example training script with MLflow tracking
- `mlflow-client/requirements.txt`: Python dependencies for training

