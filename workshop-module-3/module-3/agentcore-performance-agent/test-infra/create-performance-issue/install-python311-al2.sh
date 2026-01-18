#!/bin/bash

# Install Python 3.11 on Amazon Linux 2
# This script compiles Python 3.11 from source since it's not available in AL2 repos

set -e

echo "🐍 Installing Python 3.11 on Amazon Linux 2"
echo "============================================="

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Check if running as root or with sudo
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}❌ This script must be run as root or with sudo${NC}"
   exit 1
fi

# Check if Python 3.11 is already installed
if command -v python3.11 &> /dev/null; then
    INSTALLED_VERSION=$(python3.11 --version 2>&1 | cut -d' ' -f2)
    echo -e "${GREEN}✅ Python 3.11 is already installed (version: $INSTALLED_VERSION)${NC}"
    exit 0
fi

echo -e "${BLUE}📦 Installing build dependencies...${NC}"
yum groupinstall -y "Development Tools"
yum install -y \
    gcc \
    openssl-devel \
    bzip2-devel \
    libffi-devel \
    zlib-devel \
    wget \
    make \
    sqlite-devel \
    xz-devel \
    tk-devel \
    gdbm-devel \
    readline-devel \
    ncurses-devel

echo -e "${GREEN}✅ Build dependencies installed${NC}"

# Download Python 3.11
PYTHON_VERSION="3.11.9"
PYTHON_MAJOR_MINOR="3.11"
DOWNLOAD_DIR="/tmp/python-install"

echo -e "${BLUE}📥 Downloading Python ${PYTHON_VERSION}...${NC}"
mkdir -p "$DOWNLOAD_DIR"
cd "$DOWNLOAD_DIR"

if [[ ! -f "Python-${PYTHON_VERSION}.tgz" ]]; then
    wget "https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tgz"
else
    echo -e "${YELLOW}⚠️  Python tarball already exists, using cached version${NC}"
fi

echo -e "${BLUE}📦 Extracting Python ${PYTHON_VERSION}...${NC}"
tar -xzf "Python-${PYTHON_VERSION}.tgz"
cd "Python-${PYTHON_VERSION}"

echo -e "${BLUE}🔧 Configuring Python build...${NC}"
./configure --enable-optimizations --with-ensurepip=install

echo -e "${BLUE}🔨 Compiling Python (this may take 5-10 minutes)...${NC}"
make -j$(nproc)

echo -e "${BLUE}📦 Installing Python ${PYTHON_VERSION}...${NC}"
make altinstall

# Verify installation
if command -v python3.11 &> /dev/null; then
    INSTALLED_VERSION=$(python3.11 --version 2>&1 | cut -d' ' -f2)
    echo -e "${GREEN}✅ Python 3.11 successfully installed (version: $INSTALLED_VERSION)${NC}"
    
    # Verify pip3.11
    if command -v pip3.11 &> /dev/null; then
        echo -e "${GREEN}✅ pip3.11 is available${NC}"
    else
        echo -e "${YELLOW}⚠️  pip3.11 not found, installing...${NC}"
        python3.11 -m ensurepip --default-pip
        python3.11 -m pip install --upgrade pip
    fi
else
    echo -e "${RED}❌ Python 3.11 installation failed${NC}"
    exit 1
fi

# Cleanup
echo -e "${BLUE}🧹 Cleaning up temporary files...${NC}"
cd /
rm -rf "$DOWNLOAD_DIR"

echo ""
echo -e "${GREEN}🎉 Python 3.11 installation completed!${NC}"
echo ""
echo -e "${BLUE}📋 Verification:${NC}"
python3.11 --version
pip3.11 --version
echo ""
echo -e "${GREEN}✨ You can now run the setup-dependencies.sh script${NC}"
