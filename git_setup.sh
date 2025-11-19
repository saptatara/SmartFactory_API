#!/bin/bash

# Git Configuration and Remote Setup Script
echo "=== Git Repository Setup Script ==="

# Your credentials
USERNAME="saptatara"
EMAIL="saptatara@users.gmail.com"  # You can change this to your actual email
TOKEN="***REMOVED***"
REMOTE_URL="https://github.com/saptatara/SmartFactory_API.git"

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

# Check if we're in a git repository
if [ ! -d ".git" ]; then
    print_error "Not a git repository! Please run this script from your git repo directory."
    exit 1
fi

# Set global Git configuration
print_status "Setting global Git configuration..."
git config --global user.name "$USERNAME"
git config --global user.email "$EMAIL"

# Set repository-specific configuration
print_status "Setting repository-specific configuration..."
git config user.name "$USERNAME"
git config user.email "$EMAIL"

# Store credentials permanently
print_status "Setting up credential storage..."
git config --global credential.helper store

# Check if remote origin is set
print_status "Checking remote origin..."
if git remote get-url origin &>/dev/null; then
    CURRENT_REMOTE=$(git remote get-url origin)
    print_status "Remote origin is already set to: $CURRENT_REMOTE"
    
    # Check if it needs to be updated
    if [ "$CURRENT_REMOTE" != "$REMOTE_URL" ]; then
        print_status "Updating remote origin to the correct URL..."
        git remote set-url origin "$REMOTE_URL"
        print_success "Remote origin updated!"
    fi
else
    print_status "Setting remote origin..."
    git remote add origin "$REMOTE_URL"
    print_success "Remote origin set!"
fi

# Update remote URL to include token for authentication
print_status "Setting up authentication in remote URL..."
AUTH_URL="https://$USERNAME:$TOKEN@github.com/saptatara/SmartFactory_API.git"
git remote set-url origin "$AUTH_URL"

# Test the connection
print_status "Testing Git connection..."
git fetch origin

if [ $? -eq 0 ]; then
    print_success "Git connection test successful!"
else
    print_error "Git connection test failed. Please check your credentials."
    exit 1
fi

# Set up default push behavior
print_status "Setting up push behavior..."
git config --global push.default simple

# Display final configuration
echo ""
print_success "=== Git Setup Complete ==="
echo "Username: $(git config user.name)"
echo "Email: $(git config user.email)"
echo "Remote URL: $(git remote get-url origin | sed 's/\/\/.*@/\/\/*@/')"  # Hide credentials in output

echo ""
echo "You can now use these commands without authentication:"
echo "  git push"
echo "  git pull"
echo "  git fetch"

# Instructions for first push
echo ""
print_status "To push your changes for the first time, you can use:"
echo "  git add ."
echo "  git commit -m 'Your commit message'"
echo "  git push -u origin main"
