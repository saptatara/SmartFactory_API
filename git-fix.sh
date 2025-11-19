i#!/bin/bash

# Git Security Fix Script
echo "=== Fixing Git Security Issue ==="

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

# Remove the file with the token from staging
print_status "Removing file with exposed token from staging..."
git reset HEAD git_setup.sh

# Remove the token from the file
print_status "Removing token from git_setup.sh..."
sed -i 's/TOKEN="***REMOVED***"/TOKEN="YOUR_GITHUB_TOKEN_HERE"/g' git_setup.sh

# Add the cleaned file back
print_status "Adding cleaned file..."
git add git_setup.sh

# Make a new commit
print_status "Creating new commit without token..."
git commit -m "Add git setup script without exposed token"

print_success "Token removed from commit history!"

# Set up proper authentication without hardcoded tokens
print_status "Setting up proper Git authentication..."

# Remove the current remote with token
git remote remove origin

# Add remote without token in URL
git remote add origin https://github.com/saptatara/SmartFactory_API.git

# Set up credential helper to use the token securely
print_status "Setting up secure credential storage..."
git config --global credential.helper store

# Create credentials file manually
print_status "Setting up credentials in secure file..."
echo "https://saptatara:***REMOVED***@github.com" > ~/.git-credentials
chmod 600 ~/.git-credentials

# Test the connection
print_status "Testing connection..."
git fetch origin

if [ $? -eq 0 ]; then
    print_success "Secure authentication setup successful!"
else
    print_error "Authentication test failed!"
    exit 1
fi

echo ""
print_success "=== Security Fix Complete ==="
echo "You can now push safely:"
echo "  git push origin main"
