#!/bin/bash

echo "🔍 Network Connectivity Diagnostic"
echo "=================================="

# Get IP address
get_ip() {
    if command -v ipconfig &> /dev/null; then
        # Windows
        ipconfig | grep -A 5 "Wireless LAN adapter" | grep "IPv4" | head -1 | awk '{print $NF}'
    else
        # Linux/Mac
        hostname -I | awk '{print $1}'
    fi
}

IP=$(get_ip)
echo "📍 Your IP address: $IP"

echo ""
echo "🔍 Checking Backend Status:"
echo "==========================="

# Check if backend is running
if pgrep -f "uvicorn.*app.main:app" > /dev/null; then
    echo "✅ Backend process is running"
else
    echo "❌ Backend process is NOT running"
    echo "   Start it with: python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
    exit 1
fi

# Check what's listening on port 8000
echo ""
echo "🔍 Port 8000 Status:"
echo "==================="

if command -v netstat &> /dev/null; then
    netstat -an | grep :8000
elif command -v ss &> /dev/null; then
    ss -tuln | grep :8000
else
    echo "⚠️  Could not check port status"
fi

# Test localhost access
echo ""
echo "🔍 Testing Localhost Access:"
echo "============================"

if curl -s http://localhost:8000/ > /dev/null 2>&1; then
    echo "✅ Localhost access: OK"
else
    echo "❌ Localhost access: FAILED"
fi

# Test network access
echo ""
echo "🔍 Testing Network Access:"
echo "=========================="

if curl -s http://$IP:8000/ > /dev/null 2>&1; then
    echo "✅ Network access: OK"
else
    echo "❌ Network access: FAILED"
    echo "   This is likely a firewall issue"
fi

echo ""
echo "📱 iPhone Testing Instructions:"
echo "==============================="
echo "1. Make sure iPhone is on the same WiFi network"
echo "2. Open Safari and try: http://$IP:8000/"
echo "3. If it doesn't work, try: http://$IP:8000/api/health"
echo "4. Check if you get any error messages"

echo ""
echo "🔧 Common Solutions:"
echo "==================="
echo "1. Restart backend with: python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
echo "2. Check Windows Firewall settings"
echo "3. Temporarily disable antivirus"
echo "4. Check router AP isolation settings"
echo "5. Try a different port: --port 8080"

echo ""
echo "🌐 Alternative URLs to try on iPhone:"
echo "====================================="
echo "http://$IP:8000/"
echo "http://$IP:8000/api/health"
echo "http://$IP:8000/docs"

# Check if we can ping the IP
echo ""
echo "🔍 Network Reachability:"
echo "======================="

if ping -c 1 $IP > /dev/null 2>&1; then
    echo "✅ IP address is reachable"
else
    echo "❌ IP address is not reachable"
    echo "   Check your network connection"
fi 