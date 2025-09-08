# WSL Port Forwarding Setup for Mission Control Backend
# This script forwards port 8000 from Windows to WSL

Write-Host "WSL Port Forwarding Setup" -ForegroundColor Green
Write-Host "=========================" -ForegroundColor Green

# Get WSL IP address
$wslIP = (wsl hostname -I).Trim()
Write-Host "WSL IP Address: $wslIP" -ForegroundColor Yellow

# Get Windows IP address (WiFi)
$windowsIP = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.InterfaceAlias -like "*WLAN*" -or $_.InterfaceAlias -like "*Wi-Fi*"}).IPAddress
Write-Host "Windows IP Address: $windowsIP" -ForegroundColor Yellow

Write-Host ""
Write-Host "Setting up port forwarding..." -ForegroundColor Cyan

# Remove existing port forwarding (if any)
Write-Host "Removing existing port forwarding..."
netsh interface portproxy delete v4tov4 listenport=8000 2>$null

# Add new port forwarding
Write-Host "Adding port forwarding: Windows:8000 -> WSL:$wslIP:8000"
netsh interface portproxy add v4tov4 listenport=8000 listenaddress=0.0.0.0 connectport=8000 connectaddress=$wslIP

# Verify port forwarding
Write-Host ""
Write-Host "Verifying port forwarding..."
netsh interface portproxy show v4tov4

Write-Host ""
Write-Host "Port forwarding setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "iPhone can now connect to:" -ForegroundColor Yellow
Write-Host "   http://$windowsIP:8000" -ForegroundColor White
Write-Host ""
Write-Host "To remove port forwarding later, run:" -ForegroundColor Gray
Write-Host "   netsh interface portproxy delete v4tov4 listenport=8000" -ForegroundColor Gray

Write-Host ""
Write-Host "Make sure your backend is running in WSL on port 8000" -ForegroundColor Red
Write-Host "   Run: ./run_backend_network.sh in WSL" -ForegroundColor Gray 