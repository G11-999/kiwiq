#!/bin/bash

# Worker-specific script to build CodeRunner py-runner:3.12 Docker image
# This script is executed by the worker container which has access to Docker socket

set -e

echo "🔨 Worker: Building CodeRunner py-runner:3.12 Docker image..."

# Function to check if a command exists
command_exists() {
  command -v "$1" >/dev/null 2>&1
}

# Check if Docker is available
if ! command_exists docker; then
    echo "❌ Error: Docker CLI not found in worker container."
    echo "Make sure Docker CLI is installed in the worker dockerfile."
    exit 1
fi

# Check if Docker daemon is accessible
if ! docker info >/dev/null 2>&1; then
    echo "❌ Error: Cannot connect to Docker daemon."
    echo "Make sure Docker socket is mounted: -v /var/run/docker.sock:/var/run/docker.sock"
    exit 1
fi

# Define paths first
UNTRUSTED_DIR="/app/untrusted_code_runner"

# Check if py-runner:3.12 image already exists and if runner.py has been modified recently
RUNNER_PY_PATH="$UNTRUSTED_DIR/runner.py"
FORCE_REBUILD=false

if docker image inspect py-runner:3.12 >/dev/null 2>&1; then
    # Image exists, check if we should rebuild due to runner.py changes
    if [ -f "$RUNNER_PY_PATH" ]; then
        # Get image creation time and runner.py modification time
        IMAGE_DATE=$(docker image inspect py-runner:3.12 --format='{{.Created}}' | head -c 19)
        FILE_DATE=$(date -r "$RUNNER_PY_PATH" -Iseconds | head -c 19)
        
        echo "📋 Image created: $IMAGE_DATE"
        echo "📋 runner.py modified: $FILE_DATE"
        
        # Simple comparison - if runner.py is newer, rebuild
        if [[ "$FILE_DATE" > "$IMAGE_DATE" ]]; then
            echo "🔄 runner.py has been modified since image creation. Rebuilding..."
            FORCE_REBUILD=true
        fi
    fi
    
    if [ "$FORCE_REBUILD" = false ]; then
        echo "✅ CodeRunner image py-runner:3.12 is up to date."
        
        # Show existing image info
        echo "📋 Existing image details:"
        docker image ls py-runner:3.12 --format "table {{.Repository}}:{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
        exit 0
    fi
else
    echo "📋 CodeRunner image py-runner:3.12 not found."
fi

# Verify required files exist in the worker container
if [ ! -f "$UNTRUSTED_DIR/Dockerfile" ]; then
    echo "❌ Error: Dockerfile not found at $UNTRUSTED_DIR/Dockerfile"
    echo "Make sure untrusted_code_runner files are copied to the worker container."
    exit 1
fi

if [ ! -f "$UNTRUSTED_DIR/runner.py" ]; then
    echo "❌ Error: runner.py not found at $UNTRUSTED_DIR/runner.py"
    exit 1
fi

if [ ! -f "$UNTRUSTED_DIR/requirements-base.txt" ]; then
    echo "❌ Error: requirements-base.txt not found at $UNTRUSTED_DIR/requirements-base.txt"
    exit 1
fi

echo "📁 Building from directory: $UNTRUSTED_DIR"
echo "🏗️  Starting Docker build..."

# Build the py-runner image
docker build \
    -t py-runner:3.12 \
    -f "$UNTRUSTED_DIR/Dockerfile" \
    "$UNTRUSTED_DIR"

# # Verify the image was built successfully
# if docker image inspect py-runner:3.12 >/dev/null 2>&1; then
#     echo "✅ Successfully built py-runner:3.12 image"
    
#     # Show image details
#     echo ""
#     echo "📋 New image details:"
#     docker image ls py-runner:3.12 --format "table {{.Repository}}:{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
    
#     echo ""
#     echo "🎉 CodeRunner Docker image is ready!"
#     echo "CodeRunner workflows can now execute Python code in sandboxed containers."
    
#     # Test the image with a simple command to make sure it works
#     echo ""
#     echo "🧪 Testing image with simple command..."
#     if docker run --rm py-runner:3.12 echo '{"test": "success"}' | python -c "import sys, json; print('✅ Image test passed:', json.loads(input()))" 2>/dev/null; then
#         echo "✅ Image test successful"
#     else
#         echo "⚠️  Image test had issues, but image was built"
#     fi
    
# else
#     echo "❌ Failed to build py-runner:3.12 image"
#     echo "Check the build logs above for errors."
#     exit 1
# fi
