#!/usr/bin/env python3

"""
FIWARE IoT Agent Device Registration Fix
Registers service group and device for Professor_Robot_01 with correct API key
"""

import requests
import json
import time

# FIWARE Configuration
FIWARE_IOT_AGENT_URL = "http://localhost:4041"
FIWARE_SERVICE = "smartrobotics"
FIWARE_SERVICE_PATH = "/"
API_KEY = "8jggokgpepnvsb2uv4s40d59vk"
ROBOT_ID = "Professor_Robot_01"

def check_iot_agent():
    """Check if IoT Agent is accessible"""
    try:
        response = requests.get(f"{FIWARE_IOT_AGENT_URL}/iot/about")
        print(f"✅ IoT Agent accessible: {response.status_code}")
        print(f"   Response: {response.text}")
        return True
    except Exception as e:
        print(f"❌ IoT Agent not accessible: {e}")
        return False

def get_service_groups():
    """Get current service groups"""
    try:
        headers = {
            "fiware-service": FIWARE_SERVICE,
            "fiware-servicepath": FIWARE_SERVICE_PATH
        }
        response = requests.get(f"{FIWARE_IOT_AGENT_URL}/iot/services", headers=headers)
        print(f"📋 Current service groups: {response.status_code}")
        if response.status_code == 200:
            services = response.json()
            print(f"   Services: {json.dumps(services, indent=2)}")
            return services
        else:
            print(f"   Error: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Error getting service groups: {e}")
        return None

def create_service_group():
    """Create service group with correct API key"""
    try:
        headers = {
            "Content-Type": "application/json",
            "fiware-service": FIWARE_SERVICE,
            "fiware-servicepath": FIWARE_SERVICE_PATH
        }
        
        payload = {
            "services": [{
                "apikey": API_KEY,
                "cbroker": "http://orion:1026",
                "entity_type": "Robot",
                "resource": ""
            }]
        }
        
        print(f"📤 Creating service group with API key: {API_KEY}")
        response = requests.post(f"{FIWARE_IOT_AGENT_URL}/iot/services", 
                               headers=headers, 
                               json=payload)
        
        print(f"📋 Service group creation: {response.status_code}")
        if response.status_code in [201, 409]:  # 201 = created, 409 = already exists
            print("✅ Service group ready")
            return True
        else:
            print(f"❌ Error: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error creating service group: {e}")
        return False

def get_devices():
    """Get current devices"""
    try:
        headers = {
            "fiware-service": FIWARE_SERVICE,
            "fiware-servicepath": FIWARE_SERVICE_PATH
        }
        response = requests.get(f"{FIWARE_IOT_AGENT_URL}/iot/devices", headers=headers)
        print(f"📋 Current devices: {response.status_code}")
        if response.status_code == 200:
            devices = response.json()
            print(f"   Devices: {json.dumps(devices, indent=2)}")
            return devices
        else:
            print(f"   Error: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Error getting devices: {e}")
        return None

def register_robot_device():
    """Register Professor_Robot_01 device"""
    try:
        headers = {
            "Content-Type": "application/json",
            "fiware-service": FIWARE_SERVICE,
            "fiware-servicepath": FIWARE_SERVICE_PATH
        }
        
        payload = {
            "devices": [{
                "device_id": ROBOT_ID,
                "entity_name": f"urn:ngsi-ld:Robot:{ROBOT_ID}",
                "entity_type": "Robot",
                "transport": "MQTT",
                "attributes": [
                    {"object_id": "pose", "name": "pose", "type": "geo:json"},
                    {"object_id": "battery", "name": "battery", "type": "Number"},
                    {"object_id": "mode", "name": "mode", "type": "Text"},
                    {"object_id": "robotState", "name": "robotState", "type": "Text"},
                    {"object_id": "accuracy", "name": "accuracy", "type": "Number"}
                ],
                "commands": [
                    {"object_id": "command", "name": "command", "type": "command"}
                ]
            }]
        }
        
        print(f"📤 Registering device: {ROBOT_ID}")
        response = requests.post(f"{FIWARE_IOT_AGENT_URL}/iot/devices",
                               headers=headers,
                               json=payload)
        
        print(f"📋 Device registration: {response.status_code}")
        if response.status_code in [201, 409]:  # 201 = created, 409 = already exists
            print("✅ Device registered successfully")
            return True
        else:
            print(f"❌ Error: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error registering device: {e}")
        return False

def restart_iot_agent():
    """Restart IoT Agent container to apply changes"""
    try:
        import subprocess
        print("🔄 Restarting IoT Agent container...")
        result = subprocess.run(["docker", "restart", "fiware-iot-agent"], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ IoT Agent restarted successfully")
            print("⏳ Waiting 10 seconds for startup...")
            time.sleep(10)
            return True
        else:
            print(f"❌ Error restarting IoT Agent: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Error restarting IoT Agent: {e}")
        return False

def main():
    """Main execution function"""
    print("🔧 FIWARE IoT Agent Registration Fix")
    print("=" * 50)
    print(f"Service: {FIWARE_SERVICE}")
    print(f"API Key: {API_KEY}")
    print(f"Robot ID: {ROBOT_ID}")
    print("")
    
    # Step 1: Check IoT Agent accessibility
    if not check_iot_agent():
        print("❌ Cannot proceed - IoT Agent not accessible")
        return False
    
    # Step 2: Check current service groups
    print("\n📋 Checking current configuration...")
    services = get_service_groups()
    devices = get_devices()
    
    # Step 3: Create service group
    print("\n🔧 Setting up service group...")
    if not create_service_group():
        print("❌ Failed to create service group")
        return False
    
    # Step 4: Register device
    print("\n🤖 Registering robot device...")
    if not register_robot_device():
        print("❌ Failed to register device")
        return False
    
    # Step 5: Restart IoT Agent
    print("\n🔄 Applying configuration...")
    if not restart_iot_agent():
        print("⚠️ IoT Agent restart failed, but registration may still work")
    
    # Step 6: Verify registration
    print("\n✅ Verifying final configuration...")
    services = get_service_groups()
    devices = get_devices()
    
    print("\n🎉 FIWARE Registration Fix Complete!")
    print("🧪 Ready for end-to-end testing")
    
    return True

if __name__ == "__main__":
    success = main()
    if success:
        print("\n✅ SUCCESS: Registration completed")
    else:
        print("\n❌ FAILED: Registration incomplete") 