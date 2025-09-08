#!/bin/bash

echo "🚀 Mission Control Backend Startup"
echo "=================================="

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

# Start the backend
echo "🎯 Starting Mission Control Backend..."
echo "URL: http://localhost:8000"
echo "API Documentation: http://localhost:8000/docs"
echo ""

python3 app/main.py 