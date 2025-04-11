#!/bin/bash
# setup_ec2.sh
# Script to install prerequisites for Docker Compose deployment on Amazon Linux 2023.
# Run this once after launching and SSHing into the EC2 instance.

# Exit immediately if a command exits with a non-zero status.
set -e

echo "--- Updating system packages ---"
sudo dnf update -y

echo "--- Installing Git ---"
sudo dnf install git -y

echo "--- Installing Docker Engine ---"
sudo dnf install docker -y

echo "--- Starting and Enabling Docker Service ---"
sudo systemctl start docker
sudo systemctl enable docker # Ensures Docker starts on boot

echo "--- Adding ec2-user to the 'docker' group ---"
sudo usermod -aG docker ec2-user

echo "--- Installing Docker Compose (v2 Plugin) ---"
# Docker Compose is now integrated as a plugin
sudo dnf install docker-compose-plugin -y
echo "--- Docker Compose Installation Verification ---"
# Note: This might show an error if run before logout/login due to group permissions
docker compose version || echo "Docker compose version check might require re-login to run without sudo."

echo "--- (Optional) Installing AWS CLI ---"
# Often pre-installed on Amazon Linux. Uncomment if needed.
# sudo dnf install awscli -y
# aws --version

echo "--- Setup Complete ---"
echo ""
echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
echo "IMPORTANT: Please log out and log back in now to apply Docker group changes!"
echo "           Run 'exit', then reconnect via SSH before proceeding."
echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
echo ""
