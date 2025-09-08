#!/bin/bash

echo "🌐 Mission Control Backend - Network Setup"
echo "=========================================="

# Function to get IP address
get_ip_address() {
    if command -v ipconfig &> /dev/null; then
        # Windows
        ipconfig | grep -A 5 "Wireless LAN adapter" | grep "IPv4" | head -1 | awk '{print $NF}'
    else
        # Linux/Mac
        hostname -I | awk '{print $1}'
    fi
}

# Function to check if port is accessible
check_port() {
    local port=$1
    if command -v netstat &> /dev/null; then
        netstat -an | grep ":$port " | grep LISTEN > /dev/null
    else
        ss -tuln | grep ":$port " > /dev/null
    fi
}

# Function to check firewall status
check_firewall() {
    echo "🔍 Checking firewall status..."
    
    if command -v ufw &> /dev/null; then
        # Ubuntu/Debian
        ufw status
    elif command -v firewall-cmd &> /dev/null; then
        # CentOS/RHEL/Fedora
        firewall-cmd --list-all
    elif command -v netsh &> /dev/null; then
        # Windows
        netsh advfirewall show allprofiles
    else
        echo "⚠️  Could not detect firewall type. Please manually check port 8000 access."
    fi
}

# Get current IP address
CURRENT_IP=$(get_ip_address)

if [ -z "$CURRENT_IP" ]; then
    echo "❌ Could not determine IP address"
    echo "Please manually find your IP address:"
    echo "  Windows: ipconfig"
    echo "  Linux/Mac: hostname -I"
    exit 1
fi

echo "✅ Your IP address: $CURRENT_IP"

# Check if backend is already running
if check_port 8000; then
    echo "✅ Backend is already running on port 8000"
    echo "🌐 Access URL: http://$CURRENT_IP:8000"
else
    echo "❌ Backend is not running on port 8000"
    echo "Please start the backend first:"
    echo "  ./run_backend_network.sh"
fi

echo ""
echo "🔧 Network Configuration:"
echo "========================="

# Test network connectivity
echo "🔍 Testing network connectivity..."

# Test localhost
if curl -s http://localhost:8000/ > /dev/null 2>&1; then
    echo "✅ Localhost access: OK"
else
    echo "❌ Localhost access: FAILED"
fi

# Test network access (if backend is running)
if check_port 8000; then
    if curl -s http://$CURRENT_IP:8000/ > /dev/null 2>&1; then
        echo "✅ Network access: OK"
    else
        echo "❌ Network access: FAILED"
        echo "   This might be a firewall issue"
    fi
fi

echo ""
echo "📋 Configuration Summary:"
echo "========================"
echo "Laptop IP: $CURRENT_IP"
echo "Backend URL: http://$CURRENT_IP:8000"
echo "API Docs: http://$CURRENT_IP:8000/docs"
echo "Health Check: http://$CURRENT_IP:8000/api/health"

echo ""
echo "🤖 Robot Configuration:"
echo "======================"
echo "Update your robot configuration to use:"
echo "  Backend URL: http://$CURRENT_IP:8000"
echo ""
echo "Example robot config:"
echo "  mission_control:"
echo "    backend_url: \"http://$CURRENT_IP:8000\""

echo ""
echo "🔒 Security Notes:"
echo "================="
echo "• This setup is for local network use only"
echo "• Ensure your firewall allows port 8000"
echo "• Both devices must be on the same network"
echo "• Consider using VPN for remote access"

echo ""
echo "📖 Next Steps:"
echo "=============="
echo "1. Start the backend: ./run_backend_network.sh"
echo "2. Update robot configuration with the IP above"
echo "3. Test connection from robot: curl http://$CURRENT_IP:8000/"
echo "4. Check the detailed guide: ROBOT_NETWORK_SETUP.md"

# Check firewall
echo ""
check_firewall 