# WARNING: This file intentionally has GCP security issues for testing
# It should FAIL trivy-iac and checkov-terraform hooks
resource "google_compute_instance" "insecure" {
  name         = "insecure-vm"
  machine_type = "e2-medium"
  zone         = "europe-west2-a"

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-11"
    }
  }

  network_interface {
    network = "default"
    # Public IP assigned - security risk
    access_config {}
  }

  # Serial port enabled - security risk
  metadata = {
    serial-port-enable = "true"
  }
}

resource "google_compute_firewall" "open" {
  name    = "allow-all"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["0-65535"]
  }

  source_ranges = ["0.0.0.0/0"] # Open to the world
}
