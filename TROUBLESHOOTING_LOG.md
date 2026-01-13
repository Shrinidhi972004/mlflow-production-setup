# MLflow Production Setup - Troubleshooting Log

This document captures all issues encountered during the MLflow production setup and their solutions.

---

## Issue 1: Unnecessary S3 Artifacts Configuration

### Problem
- S3 artifacts configuration was present but not needed
- AWS credentials were configured in secrets and deployment
- `--default-artifact-root=s3://your-bucket-name/mlflow-artifacts` in deployment args

### Diagnostic Steps
```bash
# Reviewed deployment configuration
kubectl get deployment mlflow -n mlflow -o yaml

# Checked secrets
kubectl get secret mlflow-db-secret -n mlflow -o yaml
```

### Solution
**Removed S3 configurations from:**

1. **mlflow-deployment.yaml:**
   - Removed `AWS_ACCESS_KEY_ID` environment variable
   - Removed `AWS_SECRET_ACCESS_KEY` environment variable
   - Removed `--default-artifact-root=s3://...` argument

2. **mlflow-db-secret.yaml:**
   - Removed `AWS_ACCESS_KEY_ID` key
   - Removed `AWS_SECRET_ACCESS_KEY` key
   - Kept only `MLFLOW_BACKEND_STORE_URI`

**Result:** MLflow now stores artifacts locally in the container with PostgreSQL backend only.

---

## Issue 2: PostgreSQL Permission Errors in Pods

### Problem
- MLflow pods were getting "permission denied" errors when creating tables in PostgreSQL
- Error: `permission denied for schema public`

### Diagnostic Steps
```bash
# Check pod logs
kubectl logs -n mlflow deployment/mlflow

# Describe pod for errors
kubectl describe pod -n mlflow -l app=mlflow
```

### Root Cause
- Database and user were created, but schema-level privileges were not granted
- Missing grants for tables, sequences, and functions in the public schema
- Missing default privileges for future objects

### Solution
**Updated PostgreSQL setup with comprehensive privileges:**

```sql
-- Create the database
CREATE DATABASE mlflow;

-- Create the user
CREATE USER mlflow WITH PASSWORD 'mlflow_password';

-- Grant database privileges
GRANT ALL PRIVILEGES ON DATABASE mlflow TO mlflow;

-- Connect to the mlflow database
\c mlflow

-- Grant schema privileges (CRITICAL: fixes pod errors)
GRANT ALL PRIVILEGES ON SCHEMA public TO mlflow;
GRANT ALL ON ALL TABLES IN SCHEMA public TO mlflow;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO mlflow;
GRANT ALL ON ALL FUNCTIONS IN SCHEMA public TO mlflow;

-- Set default privileges for future objects
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO mlflow;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO mlflow;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON FUNCTIONS TO mlflow;

-- Make mlflow the owner of the database (recommended)
ALTER DATABASE mlflow OWNER TO mlflow;
```

**Result:** MLflow pods can now create and manage database objects without permission errors.

---

## Issue 3: DNS Pointing to Wrong IP Address

### Problem
- DNS was pointing to old/incorrect IP: `13.208.207.32`
- Current EC2 IP was: `56.155.96.242` (later changed to `171.48.99.242`)
- Let's Encrypt couldn't reach the server for SSL verification

### Diagnostic Steps
```bash
# Check current EC2 public IP
curl -s http://checkip.amazonaws.com

# From local machine
nslookup mlflow.shrinidhi.space

# From EC2
dig +short mlflow.shrinidhi.space
```

### Output
```
# EC2 IP
171.48.99.242

# DNS resolution (incorrect)
13.208.207.32
```

### Solution
1. Updated DNS A record in Hostinger:
   - Name: `mlflow`
   - Type: `A`
   - Value: Changed from `13.208.207.32` to `56.155.96.242`
   - TTL: `300`

2. Waited 5-10 minutes for DNS propagation

3. Verified with:
   ```bash
   dig +short mlflow.shrinidhi.space
   # Output: 56.155.96.242
   ```

**Result:** DNS correctly points to EC2 instance.

---

## Issue 4: Port 80/443 Not Accessible

### Problem
- Certificate challenge failing with "connection refused"
- Error: `dial tcp 56.155.96.242:80: connect: connection refused`
- Ingress controller not accessible from outside

### Diagnostic Steps
```bash
# Check if ports are mapped in Kind
docker ps | grep kindest

# Test port 80 accessibility
curl -v http://localhost
curl -v http://56.155.96.242

# Check Kind config
cat kind-config.yaml

# Verify ingress controller
kubectl get pods -n ingress-nginx -o wide
kubectl get svc -n ingress-nginx
```

### Findings
```
# Docker showed ports mapped on control-plane
0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp

# But curl failed
curl: (7) Failed to connect to 56.155.96.242 port 80

# Ingress controller was on worker node
NAME                                        READY   STATUS    RESTARTS   AGE   IP           NODE
ingress-nginx-controller-d49ff56c8-8pvwt    1/1     Running   0          19m   10.244.1.4   mlflow-worker2
```

### Root Cause
- Port mappings (80/443) were configured on **control-plane** node in kind-config.yaml
- Ingress controller was running on **worker node** (mlflow-worker2)
- Traffic couldn't reach the ingress controller

### Solution
**Step 1: Patch ingress controller to require control-plane node**
```bash
kubectl patch deployment ingress-nginx-controller -n ingress-nginx \
  --type='json' \
  -p='[{"op": "add", "path": "/spec/template/spec/nodeSelector/ingress-ready", "value": "true"}]'
```

**Step 2: Label the control-plane node**
```bash
kubectl label node mlflow-control-plane ingress-ready=true
```

**Step 3: Wait for pod to reschedule**
```bash
kubectl get pods -n ingress-nginx -o wide
# Verify it's now on mlflow-control-plane
```

**Step 4: Verify port 80 is accessible**
```bash
curl -I http://localhost
# Output: HTTP/1.1 404 Not Found (expected - ingress is working!)
```

**Result:** Ingress controller now runs on control-plane node where ports 80/443 are mapped.

---

## Issue 5: Ingress Controller Pod Stuck in Pending

### Problem
- After patching, ingress controller pod remained in `Pending` state
- Pod couldn't schedule to any node

### Diagnostic Steps
```bash
# Check pod status
kubectl get pods -n ingress-nginx

# Describe the pending pod
kubectl describe pod -n ingress-nginx <pod-name> | tail -20
```

### Output
```
Events:
  Type     Reason            Age   From               Message
  ----     ------            ----  ----               -------
  Warning  FailedScheduling  34s   default-scheduler  0/3 nodes are available: 
           3 node(s) didn't match Pod's node affinity/selector. 
           preemption: 0/3 nodes are available: 3 Preemption is not helpful for scheduling.
```

### Root Cause
- Ingress controller deployment has `nodeSelector: ingress-ready=true`
- None of the nodes had this label

### Solution
```bash
# Label the control-plane node
kubectl label node mlflow-control-plane ingress-ready=true

# Verify pod scheduled
kubectl get pods -n ingress-nginx -o wide
```

**Result:** Pod successfully scheduled and running on mlflow-control-plane.

---

## Issue 6: Let's Encrypt Certificate Challenge Failed - CAA Record

### Problem
- Certificate stuck in `False` state
- Challenge showing "invalid" state
- Error: `CAA record for shrinidhi.space prevents issuance`

### Diagnostic Steps
```bash
# Check certificate status
kubectl get certificate -n mlflow

# Check challenge details
kubectl get challenges -n mlflow
kubectl describe challenge -n mlflow

# Check DNS CAA records
dig CAA shrinidhi.space
```

### Output from Challenge
```
Status:
  Presented:   false
  Processing:  false
  Reason:      Error accepting authorization: acme: authorization error for mlflow.shrinidhi.space: 
               403 urn:ietf:params:acme:error:caa: While processing CAA for mlflow.shrinidhi.space: 
               CAA record for shrinidhi.space prevents issuance
  State:       invalid
```

### Root Cause
- CAA records were accidentally deleted from Hostinger DNS panel
- Without proper CAA record, Let's Encrypt is blocked from issuing certificates
- Only DigiCert was allowed initially

### Solution
**Step 1: Add CAA record in Hostinger DNS panel**
```
Type: CAA
Name: @
Flags: 0
Tag: issue
Value: letsencrypt.org
TTL: 300
```

**Step 2: Verify CAA records propagated**
```bash
dig CAA shrinidhi.space
```

**Expected output:**
```
shrinidhi.space.  300  IN  CAA  0 issue "letsencrypt.org"
shrinidhi.space.  300  IN  CAA  0 issue "digicert.com"
# ... other CAs
```

**Step 3: Delete and recreate certificate**
```bash
# Delete existing certificate
kubectl delete certificate mlflow-tls-secret -n mlflow

# Delete secret (if exists)
kubectl delete secret mlflow-tls-secret -n mlflow

# Wait for automatic recreation (via ingress annotation)
sleep 10
kubectl get certificate -n mlflow
```

**Step 4: Verify certificate issued**
```bash
kubectl get certificate -n mlflow
# NAME                READY   SECRET              AGE
# mlflow-tls-secret   True    mlflow-tls-secret   30s
```

**Step 5: Test HTTPS access**
```bash
curl -I https://mlflow.shrinidhi.space
# HTTP/2 200
```

**Result:** Certificate successfully issued and HTTPS working.

---

## Issue 7: Initial Challenge Self-Check Failed

### Problem
- First challenge attempt failed with connection refused
- This happened before we fixed the port mapping issue

### Diagnostic Steps
```bash
kubectl describe challenge -n mlflow
```

### Output
```
Reason: Waiting for HTTP-01 challenge propagation: 
        failed to perform self check GET request 
        'http://mlflow.shrinidhi.space/.well-known/acme-challenge/...: 
        dial tcp 56.155.96.242:80: connect: connection refused
```

### Root Cause
- This was before ingress controller was moved to control-plane
- Port 80 wasn't accessible yet

### Solution
- This resolved automatically after fixing Issue #4 (moving ingress controller to control-plane)
- After port 80 became accessible, new challenge succeeded

---

## Summary of All Fixes

| Issue | Root Cause | Solution | Files Modified |
|-------|-----------|----------|----------------|
| S3 Config | Unnecessary S3 setup | Removed AWS env vars and S3 args | mlflow-deployment.yaml, mlflow-db-secret.yaml |
| PostgreSQL Permissions | Missing schema grants | Added comprehensive GRANT statements | README.md (Step 3) |
| DNS Mismatch | Wrong IP in DNS | Updated A record in Hostinger | External DNS |
| Port 80/443 Not Accessible | Ingress on worker node | Moved ingress to control-plane | Patched deployment |
| Pod Pending | Missing node label | Added ingress-ready=true label | Control-plane node |
| CAA Block | Missing CAA record | Added letsencrypt.org CAA record | Hostinger DNS |
| Challenge Failed | Port not accessible yet | Fixed after port mapping issue | Automatic retry |

---

## Key Commands Used for Troubleshooting

### Checking Certificate Status
```bash
kubectl get certificate -n mlflow
kubectl describe certificate mlflow-tls-secret -n mlflow
kubectl get challenges -n mlflow
kubectl describe challenge -n mlflow
kubectl get certificaterequest -n mlflow
kubectl describe certificaterequest -n mlflow
kubectl get order -n mlflow
kubectl describe order -n mlflow
```

### Checking Ingress and Network
```bash
kubectl get ingress -n mlflow
kubectl describe ingress mlflow-ingress -n mlflow
kubectl get svc -n ingress-nginx
kubectl get pods -n ingress-nginx -o wide
kubectl get endpoints -n mlflow
```

### Checking DNS
```bash
nslookup mlflow.shrinidhi.space
dig +short mlflow.shrinidhi.space
dig CAA shrinidhi.space
```

### Checking EC2 and Connectivity
```bash
curl -s http://checkip.amazonaws.com
curl -v http://localhost
curl -I http://mlflow.shrinidhi.space
curl -I https://mlflow.shrinidhi.space
```

### Checking Kind/Docker
```bash
docker ps | grep kindest
kubectl get nodes
kubectl get nodes --show-labels
```

### Checking Logs
```bash
kubectl logs -n mlflow deployment/mlflow
kubectl logs -n cert-manager deployment/cert-manager
kubectl logs -n ingress-nginx deployment/ingress-nginx-controller
kubectl describe pod -n mlflow -l app=mlflow
```

---

## Lessons Learned

1. **Kind Port Mapping**: Ports must be mapped on the node where the ingress controller runs
2. **Node Selectors**: Always check nodeSelector requirements and ensure nodes have required labels
3. **PostgreSQL Grants**: Database creation alone isn't enough - schema-level grants are critical
4. **DNS CAA Records**: CAA records control which CAs can issue certificates - must include letsencrypt.org
5. **Certificate Retries**: Failed challenges stay "invalid" - must delete certificate to trigger new attempt
6. **DNS Propagation**: Always wait 5-10 minutes after DNS changes before testing
7. **Troubleshooting Flow**: Check from bottom up - network → ingress → certificate → application

---

## Final Working Configuration

### EC2 Security Group (Inbound Rules)
- SSH: Port 22 (from your IP)
- HTTP: Port 80 (from 0.0.0.0/0) - Required for Let's Encrypt
- HTTPS: Port 443 (from 0.0.0.0/0)
- PostgreSQL: Port 5432 (from EC2 to RDS)

### DNS Records (Hostinger)
```
Type: A
Name: mlflow
Value: 56.155.96.242
TTL: 300

Type: CAA
Name: @
Value: 0 issue "letsencrypt.org"
TTL: 300
```

### Kubernetes Resources
- Namespace: mlflow
- Deployment: mlflow (1-5 replicas via HPA)
- Service: mlflow (ClusterIP)
- Ingress: nginx with TLS
- Certificate: Auto-managed by cert-manager
- HPA: CPU 70%, Memory 80%

### Access URLs
- **HTTPS (Production)**: https://mlflow.shrinidhi.space
- **HTTP (Redirects to HTTPS)**: http://mlflow.shrinidhi.space

---

**Setup Completed:** January 13, 2026
**Status:** ✅ All issues resolved, MLflow running on HTTPS with valid Let's Encrypt certificate
