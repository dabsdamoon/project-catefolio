#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_usage() {
    echo -e "${BLUE}Usage:${NC} $0 <component> <version>"
    echo "  component: api | web"
    echo "  version: x.y.z (e.g., 1.0.0, 1.1.0)"
    echo ""
    echo "Examples:"
    echo "  $0 api 1.0.0    # Creates tag api-v1.0.0"
    echo "  $0 web 1.0.0   # Creates tag web-v1.0.0"
}

if [ $# -ne 2 ]; then
    print_usage
    exit 1
fi

COMPONENT=$1
VERSION=$2

# Validate component
if [ "$COMPONENT" != "api" ] && [ "$COMPONENT" != "web" ]; then
    echo -e "${RED}Error: Component must be 'api' or 'web'${NC}"
    print_usage
    exit 1
fi

# Validate version format (semver)
if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo -e "${RED}Error: Version must be in format x.y.z (e.g., 1.0.0)${NC}"
    exit 1
fi

TAG="${COMPONENT}-v${VERSION}"

# Check if we're on the correct branch
CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" != "main" ]; then
    echo -e "${YELLOW}Warning: You are on branch '$CURRENT_BRANCH'. Deployments typically happen from 'main'.${NC}"
    read -p "Continue anyway? (y/N): " confirm
    if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
        echo "Aborted."
        exit 1
    fi
fi

# Check for uncommitted changes
if ! git diff-index --quiet HEAD --; then
    echo -e "${RED}Error: You have uncommitted changes. Please commit or stash them first.${NC}"
    exit 1
fi

# Check if tag already exists
if git rev-parse "$TAG" >/dev/null 2>&1; then
    echo -e "${RED}Error: Tag '$TAG' already exists.${NC}"
    exit 1
fi

# Show recent tags for context
echo -e "${BLUE}Recent ${COMPONENT} tags:${NC}"
git tag -l "${COMPONENT}-v*" --sort=-version:refname | head -5 || echo "  (no previous tags)"
echo ""

# Pull latest changes
echo -e "${YELLOW}Pulling latest changes...${NC}"
git pull origin "$CURRENT_BRANCH"

# Create and push tag
echo -e "${GREEN}Creating tag: $TAG${NC}"
git tag -a "$TAG" -m "Release $COMPONENT version $VERSION"

echo -e "${YELLOW}Pushing tag to remote...${NC}"
git push origin "$TAG"

echo ""
echo -e "${GREEN}Successfully created and pushed tag: $TAG${NC}"
echo -e "${GREEN}GitHub Actions will now deploy $COMPONENT to production.${NC}"
echo ""
echo "Monitor the deployment at:"
echo "  https://github.com/dabsdamoon/project-catefolio/actions"
