#!/bin/bash

# Docker Installation Script for Ubuntu (Root version)
echo "=== Docker One-Click Installation Script (Root) ==="

# Function to print colored output
print_status() {
    echo -e "\033[1;34m[*] $1\033[0m"
}

print_success() {
    echo -e "\033[1;32m[+] $1\033[0m"
}

print_error() {
    echo -e "\033[1;31m[!] $1\033[0m"
}

# Update system
print_status "Updating package list..."
apt update

# Install prerequisites
print_status "Installing prerequisites..."
apt install -y apt-transport-https ca-certificates curl gnupg lsb-release software-properties-common

# Add Docker's official GPG key
print_status "Adding Docker's GPG key..."
mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Add Docker repository
print_status "Adding Docker repository..."
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

# Update package list again
print_status "Updating package list with Docker repository..."
apt update

# Install Docker
print_status "Installing Docker..."
apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Start and enable Docker service
print_status "Starting Docker service..."
systemctl start docker
systemctl enable docker

# For root user, no need to add to docker group
print_status "Skipping user group configuration (running as root)"

# Install Docker Compose if not already installed
if ! command -v docker-compose &> /dev/null; then
    print_status "Installing Docker Compose..."
    apt install -y docker-compose-plugin
fi

# Verify installation
print_status "Verifying Docker installation..."
docker --version
docker compose version

# Test Docker installation
print_status "Testing Docker with hello-world container..."
docker run hello-world

if [ $? -eq 0 ]; then
    print_success "Docker installed successfully!"
    print_success "Since you're running as root, you can use Docker commands directly."
else
    print_error "Docker installation test failed!"
    exit 1
fi

echo ""
print_success "=== Installation Complete ==="
echo "You can now use Docker commands as root."
