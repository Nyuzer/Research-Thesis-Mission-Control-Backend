#!/usr/bin/env python3

import rospy
import os
import subprocess
import signal
import time
from std_msgs.msg import String

class MapSwitchService:
    """
    ROS Service for Dynamic Map Switching
    
    Subscribes to /robot/switch_map_request topic for map switch requests
    Publishes status to /robot/map_switch_status topic
    
    Provides functionality to:
    - Stop the current map_server
    - Start a new map_server with the specified map
    - Manage the map_server lifecycle
    """
    
    def __init__(self):
        rospy.init_node('map_switch_service', anonymous=True)
        
        # Initialize state
        self.current_map_process = None
        self.current_map_id = None
        self.maps_base_path = '/tmp/fiware_maps'
        
        # Create subscriber for map switch requests
        self.switch_sub = rospy.Subscriber('/robot/switch_map_request', String, self.handle_map_switch_request)
        
        # Status publisher
        self.status_pub = rospy.Publisher('/robot/map_switch_status', String, queue_size=10)
        
        rospy.loginfo("Map Switch Service started")
        rospy.loginfo(f"Maps base path: {self.maps_base_path}")
        rospy.loginfo("Listening for map switch requests on /robot/switch_map_request")
        
        # Register cleanup handler
        rospy.on_shutdown(self.cleanup)
    
    def handle_map_switch_request(self, msg):
        """Handle map switch requests from topic"""
        try:
            map_id = msg.data.strip()
            rospy.loginfo(f"Map switch request received for map: {map_id}")
            
            # Stop current map server
            if self.current_map_process:
                rospy.loginfo("Stopping current map server...")
                self.stop_map_server()
            
            # Start new map server with the specified map
            success = self.start_map_server(map_id)
            
            if success:
                self.current_map_id = map_id
                status_msg = f"SUCCESS: Map switched to {map_id}"
                rospy.loginfo(status_msg)
                self.publish_status(status_msg)
            else:
                error_msg = f"ERROR: Failed to switch to map {map_id}"
                rospy.logerr(error_msg)
                self.publish_status(error_msg)
                
        except Exception as e:
            error_msg = f"ERROR: Exception in map switch service: {str(e)}"
            rospy.logerr(error_msg)
            self.publish_status(error_msg)
    
    def start_map_server(self, map_id):
        """Start map server with specified map"""
        try:
            # Determine map file path
            if map_id == 'default_map' or not map_id:
                # Use default map from professor_robot package
                map_file = self.get_default_map_path()
            else:
                # Use downloaded map from fiware_maps
                map_file = os.path.join(self.maps_base_path, map_id, 'map.yaml')
            
            # Verify map file exists
            if not os.path.exists(map_file):
                rospy.logerr(f"Map file not found: {map_file}")
                return False
            
            rospy.loginfo(f"Starting map server with map: {map_file}")
            
            # Start map_server node
            cmd = ['rosrun', 'map_server', 'map_server', map_file]
            self.current_map_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid  # Create new process group
            )
            
            # Wait a moment for the process to start
            time.sleep(2)
            
            # Check if process is still running
            if self.current_map_process.poll() is None:
                rospy.loginfo(f"Map server started successfully (PID: {self.current_map_process.pid})")
                return True
            else:
                rospy.logerr("Map server failed to start")
                return False
                
        except Exception as e:
            rospy.logerr(f"Error starting map server: {str(e)}")
            return False
    
    def stop_map_server(self):
        """Stop current map server"""
        try:
            if self.current_map_process:
                rospy.loginfo(f"Stopping map server (PID: {self.current_map_process.pid})")
                
                # Send SIGTERM to process group
                os.killpg(os.getpgid(self.current_map_process.pid), signal.SIGTERM)
                
                # Wait for process to terminate
                try:
                    self.current_map_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    rospy.logwarn("Map server didn't terminate gracefully, sending SIGKILL")
                    os.killpg(os.getpgid(self.current_map_process.pid), signal.SIGKILL)
                
                self.current_map_process = None
                rospy.loginfo("Map server stopped")
                
        except Exception as e:
            rospy.logerr(f"Error stopping map server: {str(e)}")
    
    def get_default_map_path(self):
        """Get path to default map from professor_robot package"""
        try:
            # Use rospack to find package path
            result = subprocess.run(['rospack', 'find', 'professor_robot'], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                pkg_path = result.stdout.strip()
                return os.path.join(pkg_path, 'maps', 'occupancy_grid.yaml')
            else:
                rospy.logerr("Failed to find professor_robot package")
                return None
        except Exception as e:
            rospy.logerr(f"Error finding default map: {str(e)}")
            return None
    
    def publish_status(self, message):
        """Publish status message"""
        try:
            msg = String()
            msg.data = message
            self.status_pub.publish(msg)
            rospy.logdebug(f"Published status: {message}")
        except Exception as e:
            rospy.logerr(f"Error publishing status: {str(e)}")
    
    def cleanup(self):
        """Cleanup when shutting down"""
        rospy.loginfo("Cleaning up map switch service...")
        if self.current_map_process:
            self.stop_map_server()
        rospy.loginfo("Map switch service cleanup complete")

def main():
    try:
        # Create service instance
        service = MapSwitchService()
        
        # Keep service running
        rospy.spin()
        
    except rospy.ROSInterruptException:
        rospy.loginfo("Map switch service interrupted")
    except Exception as e:
        rospy.logerr(f"Map switch service error: {str(e)}")

if __name__ == '__main__':
    main() 