#!/bin/bash

echo "🚀 Mission Control Backend - Network Mode"
echo "========================================="

# Check if python3 is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 is not installed"
    exit 1
fi

# Check if pip is available
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3 is not installed"
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔄 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📚 Installing dependencies..."
pip3 install -r requirements.txt

# Create maps directory
mkdir -p maps

# Get local IP address
LOCAL_IP=$(hostname -I | awk '{print $1}')
echo "🌐 Your laptop's IP address: $LOCAL_IP"

# Start the backend on all interfaces
echo "🎯 Starting Mission Control Backend on network..."
echo "URL: http://$LOCAL_IP:8000"
echo "API Documentation: http://$LOCAL_IP:8000/docs"
echo ""
echo "⚠️  Make sure your firewall allows connections on port 8000"
echo ""

# Run with uvicorn on all interfaces (0.0.0.0)
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload 