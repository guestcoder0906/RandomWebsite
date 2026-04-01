#!/bin/bash

# Configuration: Update these values
# ==========================================
HF_USERNAME="PinkAlpaca"
SPACE_NAME="RandomWeb"
# ==========================================

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}==========================================${NC}"
echo -e "${BLUE}  Starting Hugging Face Deployment${NC}"
echo -e "${BLUE}==========================================${NC}"

# Check for git
if ! command -v git &> /dev/null; then
    echo -e "${RED}Error: git is not installed.${NC}"
    exit 1
fi

# Ensure local git repo is initialized
if [ ! -d ".git" ]; then
    echo "Initializing local git repository..."
    git init
    git add .
    git commit -m "Initial commit for HF deployment"
fi

# Confirm username is updated
if [ "$HF_USERNAME" == "UPDATE_WITH_YOUR_HF_USERNAME" ]; then
    echo -e "${RED}Error: Please edit this script and set your HF_USERNAME.${NC}"
    exit 1
fi

# Set remote URL
REMOTE_URL="https://huggingface.co/spaces/${HF_USERNAME}/${SPACE_NAME}"
echo -e "Target Space: ${REMOTE_URL}"

# Check if 'huggingface' remote exists, add if not
if ! git remote | grep -q "huggingface"; then
    echo "Adding Hugging Face remote..."
    git remote add huggingface "${REMOTE_URL}"
else
    echo "Hugging Face remote already exists. Updating URL..."
    git remote set-url huggingface "${REMOTE_URL}"
fi

# Stage all files
git add .

# Commit changes
COMMIT_MSG="Deploy: $(date '+%Y-%m-%d %H:%M:%S')"
git commit -m "$COMMIT_MSG" --allow-empty

# Push to Hugging Face
echo -e "${GREEN}Pushing to Hugging Face...${NC}"
echo "--------------------------------------------------------"
echo "TIP: Use your Hugging Face Access Token as the password."
echo "--------------------------------------------------------"

git push huggingface main --force

if [ $? -eq 0 ]; then
    echo -e "${GREEN}SUCCESS! Your Space is building at: ${REMOTE_URL}${NC}"
    echo "View progress here: ${REMOTE_URL}?logs=build"
else
    echo -e "${RED}Deployment failed. Please check your credentials or network status.${NC}"
fi
