# CRITICAL-only GCP Terraform failure fixture
# Must trigger CRITICAL findings from trivy-iac-critical and checkov
# Expected: trivy-iac-critical=Exit1, trivy-iac-full=Exit1, checkov=Exit1

terraform {
  required_version = ">= 1.0.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0.0"
    }
  }
}

provider "google" {
  project = "test-critical-project"
  region  = "europe-west2"
}

# CRITICAL: GCS bucket with public access
# Trivy: AVD-GCP-0001 (CRITICAL) - Bucket has public access
# Checkov: CKV_GCP_28 (CRITICAL) - Ensure public access prevention is enforced on bucket
resource "google_storage_bucket" "public" {
  name          = "critical-public-bucket"
  location      = "EU"
  force_destroy = true

  uniform_bucket_level_access = false

  labels = {
    environment = "test"
  }
}

# CRITICAL: Bucket IAM binding granting allUsers access
# Checkov: CKV_GCP_28 (CRITICAL) - Public bucket access
resource "google_storage_bucket_iam_member" "public_access" {
  bucket = google_storage_bucket.public.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

# CRITICAL: Firewall allowing SSH from anywhere
# Trivy: AVD-GCP-0027 (CRITICAL) - SSH access from internet
# Checkov: CKV_GCP_2 (CRITICAL) - Ensure Google compute firewall ingress does not allow unrestricted ssh access
resource "google_compute_firewall" "open_ssh" {
  name    = "critical-open-ssh"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["0.0.0.0/0"]
}

# CRITICAL: Firewall allowing RDP from anywhere
# Checkov: CKV_GCP_3 (CRITICAL) - Ensure Google compute firewall ingress does not allow unrestricted rdp access
resource "google_compute_firewall" "open_rdp" {
  name    = "critical-open-rdp"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["3389"]
  }

  source_ranges = ["0.0.0.0/0"]
}
