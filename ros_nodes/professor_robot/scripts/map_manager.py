#!/usr/bin/env python

import rospy
from std_msgs.msg import String
import subprocess
import os
import signal
import time

class MapManager:
    """
    Dynamic Map Management Node for Robot Navigation
    
    This node handles:
    - Map server lifecycle management (start/stop/restart)
    - Dynamic map switching based on mission requirements
    - Map file validation and path resolution
    - Robust error handling and recovery
    - TF-aware timing to minimize localization disruptions
    
    Designed to run on both simulation and real robot deployments.
    """
    
    def __init__(self):
        rospy.init_node('map_manager', anonymous=False)
        
        # Map server management
        self.map_server_process = None
        self.current_map_id = None
        
        # Map paths configuration
        self.local_maps_path = rospy.get_param('~local_maps_path', '/tmp/fiware_maps')
        self.default_maps_path = rospy.get_param('~default_maps_path', '/mnt/c/ProjectThesisROS2Test/catkin_ws/src/professor_robot/maps')
        
        # TF-aware timing parameters
        self.tf_stabilization_time = 2.5  # Time to allow TF to stabilize
        self.process_startup_time = 2.0    # Time for map_server to start
        self.graceful_shutdown_time = 1.5  # Time for clean shutdown
        
        # ROS interface
        self.setup_ros_interface()
        
        rospy.loginfo("Map Manager started with TF-aware timing")
        rospy.loginfo("Local maps path: %s", self.local_maps_path)
        rospy.loginfo("Default maps path: %s", self.default_maps_path)
        rospy.loginfo("Listening for map switch requests on /robot/switch_map_request")
        rospy.loginfo("TF stabilization time: %.1fs", self.tf_stabilization_time)
        
        # Start with default map if available
        self.initialize_default_map()
        
    def setup_ros_interface(self):
        """Setup ROS publishers and subscribers"""
        # Map switching integration
        self.map_switch_request_sub = rospy.Subscriber(
            '/robot/switch_map_request', 
            String, 
            self.handle_map_switch_request
        )
        self.map_switch_status_pub = rospy.Publisher(
            '/robot/map_switch_status', 
            String, 
            queue_size=10
        )
        
        rospy.loginfo("ROS interface setup complete")
    
    def initialize_default_map(self):
        """Initialize with default map if available"""
        default_map_path = os.path.join(self.default_maps_path, "occupancy_grid.yaml")
        if os.path.exists(default_map_path):
            rospy.loginfo("Starting with default map: %s", default_map_path)
            if self.start_map_server(default_map_path):
                self.current_map_id = "default"
                rospy.loginfo("Default map server started successfully")
            else:
                rospy.logwarn("Failed to start default map server")
        else:
            rospy.loginfo("No default map found, waiting for map switch requests")
    
    def handle_map_switch_request(self, msg):
        """Handle map switch requests with TF-aware timing"""
        try:
            map_id = msg.data
            rospy.loginfo("Received map switch request for map: %s", map_id)
            
            # Check if this is the current map
            if map_id == self.current_map_id:
                rospy.loginfo("Map %s is already active, no switch needed", map_id)
                success_msg = "SUCCESS: Map %s already active" % map_id
                self.map_switch_status_pub.publish(String(data=success_msg))
                return
            
            # Check if map exists
            map_path = self.find_map_path(map_id)
            if not map_path:
                error_msg = "ERROR: Map not found: %s" % map_id
                rospy.logerr(error_msg)
                self.map_switch_status_pub.publish(String(data=error_msg))
                return
            
            # Notify start of map switching process
            rospy.loginfo("🔄 Starting TF-aware map switch: %s -> %s", self.current_map_id, map_id)
            switch_start_msg = "SWITCHING: Starting map change to %s" % map_id
            self.map_switch_status_pub.publish(String(data=switch_start_msg))
            
            # Phase 1: Graceful shutdown of current map server
            if self.map_server_process:
                rospy.loginfo("Phase 1: Gracefully stopping current map server...")
                self.graceful_stop_map_server()
                rospy.loginfo("Map server stopped - waiting for TF to stabilize...")
                time.sleep(self.graceful_shutdown_time)
            
            # Phase 2: Start new map server
            rospy.loginfo("Phase 2: Starting new map server with map: %s", map_path)
            if self.start_map_server_robust(map_path):
                # Phase 3: Wait for map server stabilization
                rospy.loginfo("Phase 3: Waiting for map server stabilization...")
                time.sleep(self.process_startup_time)
                
                # Verify map server is still running
                if self.is_map_server_running():
                    self.current_map_id = map_id
                    success_msg = "SUCCESS: Map switched to %s" % map_id
                    rospy.loginfo("✅ %s", success_msg)
                    
                    # Publish success status
                    self.map_switch_status_pub.publish(String(data=success_msg))
                    
                    # Phase 4: Extended TF stabilization period
                    rospy.loginfo("Phase 4: Allowing TF system to stabilize...")
                    time.sleep(self.tf_stabilization_time)
                    
                    # Final confirmation
                    final_msg = "READY: Map %s fully loaded and ready for navigation" % map_id
                    rospy.loginfo("🎯 %s", final_msg)
                    self.map_switch_status_pub.publish(String(data=final_msg))
                    
                    rospy.loginfo("✨ Map switch completed successfully - TF should be stable")
                    rospy.loginfo("RViz users: Refresh /map topic if needed (remove and re-add Map display)")
                else:
                    error_msg = "ERROR: Map server died after startup with map %s" % map_id
                    rospy.logerr(error_msg)
                    self.map_switch_status_pub.publish(String(data=error_msg))
            else:
                error_msg = "ERROR: Failed to start map server with map %s" % map_id
                rospy.logerr(error_msg)
                self.map_switch_status_pub.publish(String(data=error_msg))
                
        except Exception as e:
            error_msg = "ERROR: Map switch exception: %s" % str(e)
            rospy.logerr(error_msg)
            self.map_switch_status_pub.publish(String(data=error_msg))
    
    def find_map_path(self, map_id):
        """Find the path to the map YAML file"""
        # Handle special case for default map
        if map_id == "default":
            default_path = os.path.join(self.default_maps_path, "occupancy_grid.yaml")
            if os.path.exists(default_path):
                rospy.loginfo("Found default map: %s", default_path)
                return default_path
        
        # Check local maps path first (downloaded maps use map.yaml)
        local_path = os.path.join(self.local_maps_path, map_id, "map.yaml")
        if os.path.exists(local_path):
            rospy.loginfo("Found dynamic map in local path: %s", local_path)
            return local_path
        
        # Check default maps path fallback (use occupancy_grid.yaml)
        default_path = os.path.join(self.default_maps_path, "occupancy_grid.yaml")
        if os.path.exists(default_path):
            rospy.loginfo("Falling back to default map: %s", default_path)
            return default_path
        
        # Check if map_id is a direct path
        if os.path.exists(map_id):
            rospy.loginfo("Map ID is direct path: %s", map_id)
            return map_id
        
        return None
    
    def start_map_server_robust(self, map_path):
        """Start map server with robust error handling"""
        try:
            rospy.loginfo("Starting map server with map: %s", map_path)
            
            # Build rosrun command with specific name to avoid conflicts
            cmd = [
                "rosrun", "map_server", "map_server", 
                map_path,
                "__name:=map_server"
            ]
            
            # Start map server process with proper process group
            self.map_server_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid,  # Create new process group
                env=dict(os.environ, ROS_NAMESPACE='')  # Clean namespace
            )
            
            # Give it time to start and check multiple times
            for attempt in range(5):  # 5 attempts over 2 seconds
                time.sleep(0.4)
                if self.map_server_process.poll() is None:
                    rospy.loginfo("Map server starting... attempt %d/5", attempt + 1)
                else:
                    # Process died early
                    stdout, stderr = self.map_server_process.communicate()
                    rospy.logerr("Map server died during startup:")
                    rospy.logerr("STDOUT: %s", stdout.decode() if stdout else "None")
                    rospy.logerr("STDERR: %s", stderr.decode() if stderr else "None")
                    return False
            
            # Final check
            if self.map_server_process.poll() is None:
                rospy.loginfo("Map server started successfully with PID: %d", self.map_server_process.pid)
                return True
            else:
                stdout, stderr = self.map_server_process.communicate()
                rospy.logerr("Map server failed to start properly:")
                rospy.logerr("STDOUT: %s", stdout.decode() if stdout else "None")
                rospy.logerr("STDERR: %s", stderr.decode() if stderr else "None")
                return False
                
        except Exception as e:
            rospy.logerr("Exception starting map server: %s", str(e))
            return False
    
    def start_map_server(self, map_path):
        """Start map server with specified map (legacy method)"""
        return self.start_map_server_robust(map_path)
    
    def graceful_stop_map_server(self):
        """Gracefully stop the current map server"""
        if not self.map_server_process:
            return True
            
        try:
            rospy.loginfo("Gracefully stopping map server (PID: %d)", self.map_server_process.pid)
            
            # Send SIGTERM first for graceful shutdown
            os.killpg(os.getpgid(self.map_server_process.pid), signal.SIGTERM)
            
            # Wait for graceful shutdown
            for i in range(10):  # Wait up to 1 second
                if self.map_server_process.poll() is not None:
                    rospy.loginfo("Map server stopped gracefully")
                    self.map_server_process = None
                    return True
                time.sleep(0.1)
            
            # If still running, force kill
            rospy.logwarn("Map server didn't stop gracefully, forcing shutdown")
            os.killpg(os.getpgid(self.map_server_process.pid), signal.SIGKILL)
            self.map_server_process.wait()
            self.map_server_process = None
            return True
            
        except Exception as e:
            rospy.logerr("Error stopping map server: %s", str(e))
            self.map_server_process = None
            return False
    
    def get_current_map_id(self):
        """Get the currently active map ID"""
        return self.current_map_id
    
    def is_map_server_running(self):
        """Check if map server is currently running"""
        if self.map_server_process:
            return self.map_server_process.poll() is None
        return False
    
    def cleanup(self):
        """Cleanup resources"""
        if self.map_server_process:
            rospy.loginfo("Cleaning up map server process")
            self.graceful_stop_map_server()
    
    def run(self):
        """Main run loop"""
        rospy.loginfo("Map Manager ready for map switch requests")
        
        # Publish initial status
        if self.current_map_id:
            status_msg = "READY: Map manager initialized with map %s" % self.current_map_id
            self.map_switch_status_pub.publish(String(data=status_msg))
        
        rospy.spin()

if __name__ == '__main__':
    try:
        manager = MapManager()
        # Register cleanup function
        rospy.on_shutdown(manager.cleanup)
        manager.run()
    except rospy.ROSInterruptException:
        rospy.loginfo("Map Manager shutting down")
    except Exception as e:
        rospy.logerr("Map Manager error: %s", str(e)) 