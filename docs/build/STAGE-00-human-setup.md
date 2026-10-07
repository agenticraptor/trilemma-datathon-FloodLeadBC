# Stage 0 — human setup (reference only)

> **Superseded on Oct 7, 2026:** the VM already exists and no storage bucket is used. Stage 0 is now the worker's discovery prompt, `docs/build/prompts/STAGE-00-environment.md`. Keep this file only as a reference for rebuilding the VM from scratch.

Do these yourself. They need your accounts and billing. Replace `YOUR_PROJECT_ID` and `YOUR_BILLING_ACCOUNT`. All resources are in Toronto (`northamerica-northeast2`) to keep data in Canada.

## 1. GCP project, APIs, network address

```bash
gcloud projects create YOUR_PROJECT_ID --name="FloodLead BC"
gcloud billing projects link YOUR_PROJECT_ID --billing-account=YOUR_BILLING_ACCOUNT
gcloud config set project YOUR_PROJECT_ID
gcloud services enable compute.googleapis.com storage.googleapis.com iam.googleapis.com

gcloud compute addresses create floodlead-ip --region=northamerica-northeast2
gcloud compute addresses describe floodlead-ip --region=northamerica-northeast2 --format='value(address)'
```

Write down the IP. The public URL will be `https://<IP with dots replaced by dashes>.sslip.io` (free DNS that maps to your IP; Caddy gets a real HTTPS certificate for it). If you own a domain, point an A record at the IP and use that instead.

## 2. Service account and archive bucket

```bash
gcloud iam service-accounts create floodlead-vm --display-name="FloodLead VM"

gcloud storage buckets create gs://YOUR_PROJECT_ID-archive \
  --location=northamerica-northeast2 --uniform-bucket-level-access

gcloud storage buckets add-iam-policy-binding gs://YOUR_PROJECT_ID-archive \
  --member=serviceAccount:floodlead-vm@YOUR_PROJECT_ID.iam.gserviceaccount.com \
  --role=roles/storage.objectAdmin
```

## 3. VM and firewall

```bash
gcloud compute firewall-rules create floodlead-allow-web --network=default \
  --allow=tcp:80,tcp:443 --target-tags=floodlead-web --source-ranges=0.0.0.0/0

gcloud compute instances create floodlead-vm \
  --zone=northamerica-northeast2-a --machine-type=e2-standard-4 \
  --image-family=debian-12 --image-project=debian-cloud \
  --boot-disk-size=100GB --boot-disk-type=pd-balanced \
  --address=floodlead-ip --tags=floodlead-web \
  --service-account=floodlead-vm@YOUR_PROJECT_ID.iam.gserviceaccount.com \
  --scopes=cloud-platform

gcloud compute ssh floodlead-vm --zone=northamerica-northeast2-a
```

e2-standard-4 is 4 vCPU / 16 GB. No GPU is needed: every model in the plan trains on CPU. Set a budget alert in the console (Billing → Budgets & alerts), e.g. CA$150.

## 4. On the VM

```bash
sudo apt-get update && sudo apt-get install -y git curl jq gh
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER && sudo systemctl enable docker
curl -LsSf https://astral.sh/uv/install.sh | sh
curl -fsSL https://claude.ai/install.sh | bash
exit   # log out and back in so the docker group and PATH apply
```

Then reconnect and:

```bash
gh auth login                      # GitHub.com → HTTPS → log in with a browser code
git clone https://github.com/agenticraptor/trilemma-datathon-FloodLeadBC.git ~/trilemma-datathon
cd ~/trilemma-datathon
cat > .env <<'EOF'
GCS_BUCKET=YOUR_PROJECT_ID-archive
PUBLIC_HOSTNAME=<IP-with-dashes>.sslip.io
ACME_EMAIL=pranayg.aiesec@gmail.com
POSTGRES_PASSWORD=<generate: openssl rand -hex 24>
EOF
claude                             # log in, choose your model and effort, then paste the Stage 1 instruction
```

`.env` is gitignored. Never paste its contents into chat or commits.

## 5. Tell the supervisor

Reply with: the public hostname, the VM zone, and the output of `claude --version`, `docker --version` and `gh auth status`.
