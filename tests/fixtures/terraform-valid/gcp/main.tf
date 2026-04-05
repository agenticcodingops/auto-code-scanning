# Valid GCP Terraform - passes ALL security checks
# Fixture for testing that clean code produces exit 0 from all hooks

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
  project = "test-secure-project"
  region  = "europe-west2"
}

# --- GCS Bucket (fully secured) ---

resource "google_storage_bucket" "secure" {
  name          = "test-secure-bucket-fixture"
  location      = "EU"
  force_destroy = false

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }

  encryption {
    default_kms_key_name = "projects/test-secure-project/locations/europe-west2/keyRings/test-ring/cryptoKeys/test-key"
  }

  logging {
    log_bucket = "test-secure-bucket-fixture"
  }

  labels = {
    environment = "dev"
    owner       = "security-team"
  }
}

# --- Firewall (restricted) ---

resource "google_compute_firewall" "restricted" {
  name    = "test-restricted-fw"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["443"]
  }

  source_ranges = ["10.0.0.0/8"]

  target_tags = ["secure-server"]
}

# --- Compute Instance (secured) ---

resource "google_compute_instance" "secure" {
  name         = "test-secure-vm"
  machine_type = "e2-medium"
  zone         = "europe-west2-a"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
    }
  }

  network_interface {
    network = "default"
    # No access_config block = no public IP
  }

  metadata = {
    serial-port-enable = "false"
    block-project-ssh-keys = "true"
  }

  shielded_instance_config {
    enable_secure_boot          = true
    enable_vtpm                 = true
    enable_integrity_monitoring = true
  }

  service_account {
    email  = "custom-sa@test-secure-project.iam.gserviceaccount.com"
    scopes = ["cloud-platform"]
  }

  labels = {
    environment = "dev"
    owner       = "security-team"
  }
}
