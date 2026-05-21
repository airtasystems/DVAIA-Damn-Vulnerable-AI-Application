# AWS EC2 Deployment Guide

This guide walks you through deploying DVAIA (Damn Vulnerable AI Application) to AWS EC2.

**⚠️ Security Warning**: This is an **intentionally vulnerable application** for security testing and education. Deploy it in an isolated environment with strict access controls. Never use real user data.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Step 1: Launch EC2 Instance](#step-1-launch-ec2-instance)
- [Step 2: Configure Security Group](#step-2-configure-security-group)
- [Step 3: Install Docker](#step-3-install-docker)
- [Step 4: Deploy Application](#step-4-deploy-application)
- [Step 5: Access Application](#step-5-access-application)
- [Optional: Custom Domain & HTTPS](#optional-custom-domain--https)
- [Monitoring & Maintenance](#monitoring--maintenance)
- [Troubleshooting](#troubleshooting)
- [Cost Estimates](#cost-estimates)

---

## Prerequisites

- AWS account with EC2 access
- SSH key pair for EC2 access
- Basic terminal/SSH knowledge
- Git repository URL (or files ready to upload)

---

## Step 1: Launch EC2 Instance

### Recommended Instance Types

For Ollama llama3.2 (3B model):

| Instance Type | vCPU | RAM | Cost/Hour* | Recommendation |
|---------------|------|-----|------------|----------------|
| `t3.large` | 2 | 8GB | $0.0832 | Minimum viable |
| `t3.xlarge` | 4 | 16GB | $0.1664 | **Recommended** |
| `c6i.xlarge` | 4 | 8GB | $0.17 | Best CPU performance |

*Pricing for us-east-1 region, on-demand

### Launch Steps

1. **Go to EC2 Console** → Click "Launch Instance"

2. **Configure Instance:**
   - **Name**: `dvaia-demo` (or your preferred name)
   - **AMI**: Ubuntu Server 22.04 LTS (free tier eligible)
   - **Instance type**: `t3.xlarge` (recommended)
   - **Key pair**: Create new or select existing SSH key pair
   - **Network settings**: 
     - Create new security group (we'll configure in next step)
     - Allow SSH from your IP
   - **Storage**: 
     - **Size**: 20 GB minimum
     - **Type**: gp3 (better performance) or gp2

3. **Click "Launch Instance"**

4. **Wait 2-3 minutes** for instance to start

5. **Note your Public IP address** from the instance details page

---

## Step 2: Configure Security Group

### Required Ports

Edit your security group to allow these inbound rules:

| Type | Protocol | Port | Source | Purpose |
|------|----------|------|--------|---------|
| SSH | TCP | 22 | `Your IP/32` | SSH access |
| Custom TCP | TCP | 5000 | `0.0.0.0/0` or `Your IP/32` | Web UI access |
| Custom TCP | TCP | 11480 | `Your IP/32` | Ollama API (optional, debugging) |
| Custom TCP | TCP | 6333 | `Your IP/32` | Qdrant UI (optional, debugging) |

### Security Options

**Option 1 - Public Demo (Less Secure):**
- Port 5000: `0.0.0.0/0` (accessible from anywhere)
- ⚠️ Anyone can access your vulnerable app
- Use for short demos only

**Option 2 - Private (More Secure):**
- Port 5000: `Your IP/32` (only your IP)
- Better for learning/testing
- **Recommended**

**Option 3 - VPN Access (Most Secure):**
- Deploy in private subnet
- Access via VPN/bastion host
- Best for corporate environments

### Configure Security Group

1. Go to **EC2 → Security Groups**
2. Select your instance's security group
3. Click **Edit inbound rules**
4. Add the rules from the table above
5. Click **Save rules**

---

## Step 3: Install Docker

### Connect to Instance

```bash
# Replace with your actual key file and IP
ssh -i /path/to/your-key.pem ubuntu@<EC2-PUBLIC-IP>
```

### Install Docker & Docker Compose

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install Docker (official script)
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
rm get-docker.sh

# Add ubuntu user to docker group (no sudo needed)
sudo usermod -aG docker ubuntu

# Install Docker Compose plugin
sudo apt install docker-compose-plugin -y

# IMPORTANT: Log out and back in for group changes
exit
```

### Reconnect and Verify

```bash
# Reconnect via SSH
ssh -i /path/to/your-key.pem ubuntu@<EC2-PUBLIC-IP>

# Verify Docker installation
docker --version
# Output: Docker version 24.x.x, build...

docker compose version
# Output: Docker Compose version v2.x.x
```

---

## Step 4: Deploy Application

### Option A: Clone from Git (Recommended)

```bash
# Clone your repository
git clone https://github.com/your-username/DVAIA.git
cd DVAIA
```

### Option B: Upload via SCP

From your local machine:

```bash
# Upload entire directory
scp -i /path/to/your-key.pem -r /local/path/DVAIA ubuntu@<EC2-IP>:~/

# Then SSH in and cd to directory
ssh -i /path/to/your-key.pem ubuntu@<EC2-IP>
cd DVAIA
```

### Configure Environment

```bash
# Create/edit .env file
nano .env
```

**Minimal production `.env` (Ollama):**

```bash
# Application
PORT=5000
DEFAULT_MODEL=ollama:llama3.2
EMBEDDING_BACKEND=ollama

# Security - CHANGE THIS!
SECRET_KEY=$(openssl rand -hex 32)

# Optional: Override defaults if needed
# OLLAMA_HOST=http://ollama:11434
# DATABASE_URI=/tmp/app.db
# UPLOAD_DIR=/tmp/uploads
```

**Gemini-only `.env` (no Ollama required for LLM/RAG; Whisper still local):**

```bash
PORT=5000
GEMINI_ONLY=true
GOOGLE_API_KEY=your-google-ai-studio-key
GEMINI_CHAT_MODEL=gemini-2.0-flash
GEMINI_VISION_MODEL=gemini-2.0-flash
GEMINI_AGENTIC_MODEL=gemini-2.0-flash
EMBEDDING_BACKEND=gemini
SECRET_KEY=$(openssl rand -hex 32)
```

Start without Ollama: `./run_docker.sh --gemini-only` or `docker compose up -d --build` (no `--profile ollama`).

Use the **Cloud (Gemini)** toggle in the UI header after setting `GOOGLE_API_KEY`.

**Important Notes:**
- The `SECRET_KEY` should be unique for each deployment
- All data is stored in `/tmp` by default (cleared on restart)
- With Ollama profile: `OLLAMA_HOST` is set automatically by `./run_docker.sh` or `docker compose --profile ollama`

Save and exit: `Ctrl+X`, `Y`, `Enter`

### Build and Start Services

**With Ollama (default local LLMs):**

```bash
./run_docker.sh
# or: docker compose --profile ollama up -d --build
```

**Gemini-only (no Ollama / no model downloads):**

```bash
./run_docker.sh --gemini-only
# or: docker compose up -d --build   # with GEMINI_ONLY=true in .env
```

With Ollama profile, startup will:
1. Build the Flask application
2. Download Ollama container
3. Download Qdrant container
4. Auto-pull llama3.2 model (~2GB, takes 2-5 minutes)
5. Auto-pull nomic-embed-text model (~274MB)

### Monitor Startup Progress

```bash
# Watch Ollama downloading models (Ollama profile only — skip if using --gemini-only)
docker compose --profile ollama logs -f ollama

# You'll see:
# "pulling manifest"
# "pulling ... [various layers]"
# "verifying sha256 digest"
# "success" <- Wait for this!

# Press Ctrl+C to exit logs when done
```

### Verify All Services Running

```bash
docker compose ps

# Expected output:
# NAME           IMAGE              STATUS    PORTS
# dvaia-app      dvaia-dvaia        Up        0.0.0.0:5000->5000/tcp
# dvaia-ollama   ollama/ollama      Up        0.0.0.0:11480->11434/tcp
# dvaia-qdrant   qdrant/qdrant      Up        0.0.0.0:6333->6333/tcp
```

All services should show `Up` status.

---

## Step 5: Access Application

### Get Your Public IP

If you don't have it from EC2 console:

```bash
curl http://169.254.169.254/latest/meta-data/public-ipv4
```

### Access Web UI

Open in your browser:

```
http://<EC2-PUBLIC-IP>:5000
```

You should see:
- ⚠️ Red warning banner at top
- Navigation menu with panels
- "Direct Injection" panel active by default

### Test the Application

1. Click on **"Instructions"** tab to read overview
2. Try **"Direct Injection"** panel:
   - Enter prompt: "What is 2+2?"
   - Click "Send"
   - Wait for response (~5-10 seconds first time)

If you see a response, congratulations! Your deployment is successful.

---

## Optional: Custom Domain & HTTPS

### Step 1: Allocate Elastic IP

1. Go to **EC2 → Elastic IPs**
2. Click **"Allocate Elastic IP address"**
3. Click **"Allocate"**
4. Select the new IP → **Actions → Associate Elastic IP address**
5. Select your instance → **Associate**

Now your instance has a permanent IP that won't change on restart.

### Step 2: Configure DNS (Route 53 or External)

**Using AWS Route 53:**

1. Go to **Route 53 → Hosted zones**
2. Select your domain
3. Click **"Create record"**
4. Configure:
   - **Name**: `dvaia` (or subdomain of choice)
   - **Type**: `A`
   - **Value**: Your Elastic IP
5. Click **"Create records"**

Wait 5-10 minutes for DNS propagation.

### Step 3: Install nginx and SSL

```bash
# Install nginx and certbot
sudo apt install nginx certbot python3-certbot-nginx -y

# Create nginx configuration
sudo nano /etc/nginx/sites-available/dvaia
```

**nginx configuration:**

```nginx
server {
    listen 80;
    server_name dvaia.yourdomain.com;

    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**Enable site and get SSL:**

```bash
# Enable the site
sudo ln -s /etc/nginx/sites-available/dvaia /etc/nginx/sites-enabled/

# Test nginx configuration
sudo nginx -t

# Restart nginx
sudo systemctl restart nginx

# Get free SSL certificate from Let's Encrypt
sudo certbot --nginx -d dvaia.yourdomain.com

# Follow prompts, select "Redirect HTTP to HTTPS" when asked
```

**Access via HTTPS:**

```
https://dvaia.yourdomain.com
```

---

## Monitoring & Maintenance

### View Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f dvaia      # Flask app
docker compose logs -f ollama     # Ollama model server
docker compose logs -f qdrant     # Vector database

# Last 100 lines
docker compose logs --tail=100 dvaia
```

### Restart Services

```bash
# Restart all services
docker compose restart

# Restart specific service
docker compose restart dvaia
docker compose restart ollama
```

### Stop/Start Application

```bash
# Stop all containers (data in /tmp persists until restart)
docker compose stop

# Start stopped containers
docker compose start

# Stop and remove containers (clears all data!)
docker compose down

# Rebuild and restart everything
docker compose up -d --build
```

### Update Application Code

```bash
# Pull latest changes (if using git)
git pull

# Rebuild and restart
docker compose up -d --build
```

### Check Resource Usage

```bash
# System resources
htop  # or: top

# Docker stats (live)
docker stats

# Disk usage
df -h

# Docker disk usage
docker system df
```

---

## Troubleshooting

### Issue: Cannot connect to web UI

**Check if containers are running:**

```bash
docker compose ps
```

**Check Flask app logs:**

```bash
docker compose logs dvaia
```

**Check if port 5000 is open:**

```bash
sudo lsof -i :5000
```

**Solution:** Restart services:

```bash
docker compose restart
```

---

### Issue: Ollama not responding / "Connection refused"

**Check Ollama container:**

```bash
docker compose logs ollama
```

**Verify models are downloaded:**

```bash
docker compose exec ollama ollama list
```

Should show `llama3.2` and `nomic-embed-text`.

**Solution:** Restart Ollama and wait for models to load:

```bash
docker compose restart ollama
# Wait 30 seconds for models to load
```

---

### Issue: Model download fails (DNS errors)

**Error in logs:**
```
Error: pull model manifest: dial tcp: lookup registry.ollama.ai...
```

**Already fixed in docker-compose.yml** with custom DNS (8.8.8.8, 1.1.1.1).

**If still failing:**

```bash
# Check internet connectivity from container
docker compose exec ollama ping -c 3 8.8.8.8

# Manually pull model
docker compose exec ollama ollama pull llama3.2
```

---

### Issue: Out of memory

**Check available memory:**

```bash
free -h
```

**If < 2GB free**, you need a larger instance:

1. Stop instance
2. Change instance type to `t3.xlarge` or larger
3. Start instance
4. Restart Docker services

---

### Issue: Slow responses

**Possible causes:**
- Instance too small (use t3.xlarge minimum)
- High CPU usage (check with `top`)
- First request (model loading takes 5-10s)

**Check CPU:**

```bash
top
# Look for ollama or python processes using high CPU
```

**Solution:** Upgrade instance type for better performance.

---

### Issue: Port 5000 already in use

**Find what's using the port:**

```bash
sudo lsof -i :5000
```

**Solution:** Change port in `.env`:

```bash
nano .env
# Change: PORT=5001
```

Then restart:

```bash
docker compose down
docker compose up -d
```

Access via: `http://<IP>:5001`

---

## Cost Estimates

### AWS Costs (us-east-1 region)

**Compute (24/7 running):**

| Instance | Monthly Cost* | Best For |
|----------|--------------|----------|
| t3.large | ~$60 | Minimum viable |
| t3.xlarge | ~$120 | **Recommended** |
| c6i.xlarge | ~$123 | Best CPU performance |

**Storage:**
- 20GB gp3: ~$1.60/month
- 20GB gp2: ~$2.00/month

**Data Transfer:**
- First 100GB/month: Free
- Additional: $0.09/GB

**Elastic IP (optional):**
- Free when associated with running instance
- $0.005/hour when not associated

**Total Monthly Cost:**
- **Minimum setup**: ~$62-65 (t3.large)
- **Recommended setup**: ~$122-125 (t3.xlarge)

*Costs are estimates for 24/7 operation. Use Reserved Instances or Savings Plans for 30-70% discount on long-term usage.

### Cost Optimization

**1. Stop when not in use:**

```bash
# From AWS Console: EC2 → Instances → Stop instance
# Or via CLI:
aws ec2 stop-instances --instance-ids i-1234567890abcdef0

# You only pay for storage (~$2/month)
```

**2. Use Reserved Instances** (1-3 year commitment):
- Save 30-70% on compute
- Good for long-term demo/training environments

**3. Use Spot Instances** (for temporary demos):
- Save up to 90%
- Instance can be terminated by AWS
- Good for short-term testing

**4. Auto-shutdown schedule:**

```bash
# Add to crontab on EC2 instance
# Shutdown at midnight every day
crontab -e

# Add line:
0 0 * * * docker compose -f /home/ubuntu/DVAIA/docker-compose.yml down
```

---

## Security Best Practices

Even for an intentionally vulnerable app, follow these guidelines:

### 1. **Network Isolation**
- Use dedicated VPC or security group
- Restrict access to known IP addresses
- Never expose to entire internet in production

### 2. **No Real Data**
- Don't use actual user credentials
- No real PII or sensitive information
- Use dummy data for testing only

### 3. **Monitoring**
- Enable CloudWatch logs
- Set up billing alerts
- Monitor for unusual activity

### 4. **Time-Boxing**
- Set expiration date for demos
- Use AWS CloudWatch Events to auto-terminate
- Don't leave running indefinitely

### 5. **Documentation**
- Add clear warning banner (✅ already done)
- Document intentional vulnerabilities
- Keep access logs for compliance

### 6. **IAM Permissions**
- Use least-privilege IAM roles
- Don't use root AWS account
- Rotate access keys regularly

---

## Cleanup / Termination

### When Done with Deployment

**Option 1: Stop Instance (keep for later)**

```bash
# From AWS Console:
EC2 → Instances → Select instance → Instance state → Stop instance

# You'll pay only for storage (~$2/month)
```

**Option 2: Terminate Instance (delete everything)**

```bash
# From AWS Console:
EC2 → Instances → Select instance → Instance state → Terminate instance

# Also delete:
# 1. Elastic IP (if allocated) - Release address
# 2. EBS volumes (usually auto-deleted)
# 3. Security group (optional)

# You'll pay nothing after termination
```

---

## Additional Resources

- [AWS EC2 Documentation](https://docs.aws.amazon.com/ec2/)
- [Docker Documentation](https://docs.docker.com/)
- [Ollama Documentation](https://github.com/ollama/ollama/blob/main/README.md)
- [DVAIA README](./README.md)

---

## Support

For issues or questions:
1. Check the [Troubleshooting](#troubleshooting) section
2. Review Docker logs: `docker compose logs`
3. Check the main [README.md](./README.md)

---

**Last Updated:** February 2026
