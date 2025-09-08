#!/usr/bin/env python

import rospy
import tf2_ros
from geometry_msgs.msg import PoseWithCovarianceStamped, TransformStamped, Twist
from nav_msgs.msg import Odometry
from std_msgs.msg import String
import math
import time

class FakeLocalization:
    def __init__(self):
        rospy.init_node('fake_localization')
        
        # Initialize TF broadcaster
        self.tf_broadcaster = tf2_ros.TransformBroadcaster()
        
        # Publisher for robot pose in map frame (for move_base)
        self.pose_pub = rospy.Publisher('/amcl_pose', PoseWithCovarianceStamped, queue_size=1)
        
        # Publisher for fake odometry (since real driver isn't running)
        self.odom_pub = rospy.Publisher('/odom', Odometry, queue_size=1)
        
        # Subscribe to cmd_vel to simulate robot movement
        self.cmd_vel_sub = rospy.Subscriber('/cmd_vel', Twist, self.cmd_vel_callback)
        
        # Subscribe to map switch status to handle TF recovery
        self.map_switch_sub = rospy.Subscriber('/robot/map_switch_status', String, self.map_switch_callback)
        
        # Configure robot position based on coordinate mode
        use_real_coordinates = rospy.get_param('~use_real_coordinates', False)
        
        if use_real_coordinates:
            # Real EPSG:25832 coordinates (German UTM Zone 32N)
            self.x = 392926.234  # Real position in UTM
            self.y = 5707219.578  # Real position in UTM
            self.coordinate_mode = "REAL_UTM"
            rospy.loginfo("🗺️ Fake Localization: Using REAL EPSG:25832 coordinates")
            rospy.loginfo(f"   Initial position: ({self.x:.3f}, {self.y:.3f})")
        else:
            # Normalized coordinates for simulation (works with map origin [0,0,0])
            self.x = 80.0  # Simulation position in normalized map
            self.y = 17.0  # Simulation position in normalized map  
            self.coordinate_mode = "SIMULATION"
            rospy.loginfo("🗺️ Fake Localization: Using SIMULATION normalized coordinates")
            rospy.loginfo(f"   Initial position: ({self.x:.3f}, {self.y:.3f})")
        
        self.theta = 0.0
        
        # Flag to track if we need to adjust position for real-world maps
        self.map_origin_offset = [0.0, 0.0, 0.0]
        
        # Velocity tracking for simulation
        self.current_linear_vel = 0.0
        self.current_angular_vel = 0.0
        self.last_update_time = rospy.Time.now()
        
        # TF recovery and timing management
        self.map_switching = False
        self.force_tf_publish = False
        self.tf_recovery_count = 0
        self.last_tf_time = rospy.Time.now()
        
        # Timer for publishing - use high frequency for robust TF
        rospy.Timer(rospy.Duration(0.05), self.publish_pose)  # 20 Hz for robust TF
        
        # TF monitoring and recovery timer
        rospy.Timer(rospy.Duration(0.1), self.tf_health_monitor)  # 10 Hz monitoring
        
        rospy.loginfo("Fake localization node started - robot position: x=%.2f, y=%.2f", self.x, self.y)
        rospy.loginfo("Dynamic simulation enabled - robot will move based on cmd_vel commands")
        rospy.loginfo("TF recovery system active - monitoring for timing issues")
        
    def map_switch_callback(self, msg):
        """Handle map switch notifications for TF recovery"""
        status = msg.data
        
        if "SWITCHING:" in status:
            rospy.loginfo("🔄 Map switching detected - enabling TF recovery mode")
            self.map_switching = True
            self.force_tf_publish = True
            self.tf_recovery_count = 0
        elif "SUCCESS:" in status:
            rospy.loginfo("✅ Map switch success - maintaining TF stability")
            # Keep recovery mode active for a bit longer
            rospy.Timer(rospy.Duration(2.0), self.disable_recovery_mode, oneshot=True)
        elif "READY:" in status:
            rospy.loginfo("🎯 Map ready - TF should now be stable")
            # Additional stability period
            rospy.Timer(rospy.Duration(1.0), self.disable_recovery_mode, oneshot=True)
        elif "ERROR:" in status:
            rospy.logerr("❌ Map switch error - forcing TF recovery")
            self.force_tf_publish = True
            
    def disable_recovery_mode(self, event):
        """Disable recovery mode after successful map switch"""
        if self.map_switching:
            rospy.loginfo("🔒 Disabling TF recovery mode - system stable")
            self.map_switching = False
            self.force_tf_publish = False
            
    def tf_health_monitor(self, event):
        """Monitor TF health and force recovery if needed"""
        current_time = rospy.Time.now()
        
        # Check if we haven't published TF in too long (potential timing issue)
        time_since_last_tf = (current_time - self.last_tf_time).to_sec()
        
        if time_since_last_tf > 0.2:  # More than 200ms since last TF
            rospy.logwarn("⚠️ TF timing gap detected (%.3fs) - forcing recovery", time_since_last_tf)
            self.force_tf_publish = True
            self.tf_recovery_count += 1
            
        # During map switching, be extra aggressive about TF publishing
        if self.map_switching and self.tf_recovery_count < 50:  # Limit recovery attempts
            self.force_tf_publish = True
            
        # Log recovery attempts
        if self.force_tf_publish and self.tf_recovery_count % 10 == 0:
            rospy.loginfo("🔧 TF recovery attempt #%d - ensuring connectivity", self.tf_recovery_count)
        
    def cmd_vel_callback(self, msg):
        """Update robot position based on velocity commands"""
        current_time = rospy.Time.now()
        dt = (current_time - self.last_update_time).to_sec()
        
        # Only update if reasonable time delta (avoid initialization issues)
        if dt > 0.0 and dt < 1.0:
            # Update orientation first
            self.theta += msg.angular.z * dt
            
            # Normalize angle to [-pi, pi]
            while self.theta > math.pi:
                self.theta -= 2 * math.pi
            while self.theta < -math.pi:
                self.theta += 2 * math.pi
            
            # Update position (robot frame to world frame)
            dx = msg.linear.x * math.cos(self.theta) * dt
            dy = msg.linear.x * math.sin(self.theta) * dt
            
            self.x += dx
            self.y += dy
            
            # Store velocities for odometry
            self.current_linear_vel = msg.linear.x
            self.current_angular_vel = msg.angular.z
            
            # Log significant movements for debugging
            if abs(dx) > 0.001 or abs(dy) > 0.001 or abs(msg.angular.z) > 0.01:
                rospy.loginfo("Robot moved: position=(%.3f, %.3f), theta=%.3f, cmd=(%.3f, %.3f)", 
                            self.x, self.y, self.theta, msg.linear.x, msg.angular.z)
                
            # Force TF update during movement to ensure connectivity
            if abs(msg.linear.x) > 0.01 or abs(msg.angular.z) > 0.01:
                self.force_tf_publish = True
        
        self.last_update_time = current_time
        
    def publish_pose(self, event):
        current_time = rospy.Time.now()
        
        # Always use real current time - no artificial time manipulation
        # This prevents "jump back in time" errors that corrupt navigation
        
        # Publish transform from map to odom with real timing
        t = TransformStamped()
        t.header.stamp = current_time
        t.header.frame_id = "map"
        t.child_frame_id = "odom"
        t.transform.translation.x = self.x  # Robot position in map
        t.transform.translation.y = self.y
        t.transform.translation.z = 0.0
        t.transform.rotation.x = 0.0
        t.transform.rotation.y = 0.0
        t.transform.rotation.z = math.sin(self.theta / 2.0)
        t.transform.rotation.w = math.cos(self.theta / 2.0)
        
        # Publish transform from odom to base_link with same timestamp
        t2 = TransformStamped()
        t2.header.stamp = current_time
        t2.header.frame_id = "odom"
        t2.child_frame_id = "base_link"
        t2.transform.translation.x = 0.0  # Robot at odom origin
        t2.transform.translation.y = 0.0
        t2.transform.translation.z = 0.0
        t2.transform.rotation.x = 0.0
        t2.transform.rotation.y = 0.0
        t2.transform.rotation.z = 0.0
        t2.transform.rotation.w = 1.0
        
        # Send both transforms as a batch for atomic update
        try:
            self.tf_broadcaster.sendTransform([t, t2])
            self.last_tf_time = current_time
            
            # Reset force flag after successful publish
            if self.force_tf_publish:
                self.force_tf_publish = False
                
        except Exception as e:
            rospy.logerr("Failed to publish TF transforms: %s", str(e))
            # Retry on next cycle
            return
        
        # Publish robot pose in map frame (AMCL format)
        pose_msg = PoseWithCovarianceStamped()
        pose_msg.header.stamp = current_time
        pose_msg.header.frame_id = "map"
        pose_msg.pose.pose.position.x = self.x
        pose_msg.pose.pose.position.y = self.y
        pose_msg.pose.pose.position.z = 0.0
        pose_msg.pose.pose.orientation.x = 0.0
        pose_msg.pose.pose.orientation.y = 0.0
        pose_msg.pose.pose.orientation.z = math.sin(self.theta / 2.0)
        pose_msg.pose.pose.orientation.w = math.cos(self.theta / 2.0)
        
        # Set covariance (small values indicating good localization)
        pose_msg.pose.covariance = [0.1, 0.0, 0.0, 0.0, 0.0, 0.0,
                                   0.0, 0.1, 0.0, 0.0, 0.0, 0.0,
                                   0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                                   0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                                   0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                                   0.0, 0.0, 0.0, 0.0, 0.0, 0.1]
        
        self.pose_pub.publish(pose_msg)
        
        # Publish fake odometry with current velocities
        odom_msg = Odometry()
        odom_msg.header.stamp = current_time
        odom_msg.header.frame_id = "odom"
        odom_msg.child_frame_id = "base_link"
        odom_msg.pose.pose.position.x = 0.0  # Robot at odom origin
        odom_msg.pose.pose.position.y = 0.0
        odom_msg.pose.pose.position.z = 0.0
        odom_msg.pose.pose.orientation.x = 0.0
        odom_msg.pose.pose.orientation.y = 0.0
        odom_msg.pose.pose.orientation.z = 0.0
        odom_msg.pose.pose.orientation.w = 1.0
        
        # Set current velocities for better navigation feedback
        odom_msg.twist.twist.linear.x = self.current_linear_vel
        odom_msg.twist.twist.linear.y = 0.0
        odom_msg.twist.twist.angular.z = self.current_angular_vel
        
        # Set covariance for odometry
        odom_msg.pose.covariance = [0.1, 0.0, 0.0, 0.0, 0.0, 0.0,
                                   0.0, 0.1, 0.0, 0.0, 0.0, 0.0,
                                   0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                                   0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                                   0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                                   0.0, 0.0, 0.0, 0.0, 0.0, 0.1]
        
        self.odom_pub.publish(odom_msg)

if __name__ == '__main__':
    try:
        localization = FakeLocalization()
        rospy.spin()
    except rospy.ROSInterruptException:
        pass 