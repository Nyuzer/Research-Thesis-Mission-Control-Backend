#!/usr/bin/env python3
"""
Test script for Mission Control Backend
"""
import asyncio
import httpx
import json
import sys
import os

# Add the parent directory to the path to import the app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_URL = "http://localhost:8000"

async def test_backend():
    """Test the FastAPI backend endpoints"""
    
    async with httpx.AsyncClient() as client:
        
        print("🔍 Testing Mission Control Backend...")
        
        # Test 1: Health check
        print("\n1. Testing health endpoint...")
        try:
            response = await client.get(f"{BASE_URL}/api/health")
            print(f"✅ Health check: {response.status_code}")
            print(f"   Response: {response.json()}")
        except Exception as e:
            print(f"❌ Health check failed: {e}")
            return
        
        # Test 2: List maps (should be empty initially)
        print("\n2. Testing maps list endpoint...")
        try:
            response = await client.get(f"{BASE_URL}/api/maps")
            print(f"✅ Maps list: {response.status_code}")
            print(f"   Response: {response.json()}")
        except Exception as e:
            print(f"❌ Maps list failed: {e}")
        
        # Test 3: Test FIWARE connection
        print("\n3. Testing FIWARE connection...")
        try:
            response = await client.post(f"{BASE_URL}/api/test/fiware")
            result = response.json()
            print(f"✅ FIWARE test: {response.status_code}")
            print(f"   Status: {result.get('status')}")
            print(f"   Message: {result.get('message')}")
            if result.get('status') == 'error':
                print(f"   Error: {result.get('error')}")
        except Exception as e:
            print(f"❌ FIWARE test failed: {e}")
        
        # Test 4: Test mission endpoint (without valid map)
        print("\n4. Testing mission endpoint...")
        mission_data = {
            "robotId": "Professor_Robot:01",
            "destination": {
                "type": "Point",
                "coordinates": [78.0, 17.3, 0]
            },
            "mapId": "test_map_001"
        }
        
        try:
            response = await client.post(
                f"{BASE_URL}/api/missions/send",
                json=mission_data
            )
            print(f"✅ Mission send: {response.status_code}")
            if response.status_code == 404:
                print("   Expected: Map not found (no maps uploaded yet)")
            else:
                print(f"   Response: {response.json()}")
        except Exception as e:
            print(f"❌ Mission send failed: {e}")
        
        print("\n🎉 Backend testing completed!")
        print("\nNext steps:")
        print("1. Upload a map using: POST /api/maps/upload")
        print("2. Send missions using: POST /api/missions/send")
        print("3. Monitor missions using: GET /api/missions")

if __name__ == "__main__":
    print("Mission Control Backend Test")
    print("Make sure the backend is running: python mission_control_backend/app/main.py")
    print("Starting tests in 3 seconds...")
    
    import time
    time.sleep(3)
    
    asyncio.run(test_backend()) 