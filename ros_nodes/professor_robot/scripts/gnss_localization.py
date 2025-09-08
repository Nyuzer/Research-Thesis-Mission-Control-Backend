#!/usr/bin/env python

import rospy
import tf2_ros
from geometry_msgs.msg import PoseWithCovarianceStamped, TransformStamped, Twist, PoseStamped
from nav_msgs.msg import Odometry
from std_msgs.msg import String
from sensor_msgs.msg import NavSatFix, Imu
import math
import time
import pyproj

class GNSSLocalization:
    def __init__(self):
        rospy.init_node('gnss_localization')
        
        # Initialize TF broadcaster
        self.tf_broadcaster = tf2_ros.TransformBroadcaster()
        
        # Publisher for robot pose in map frame (for move_base)
        self.pose_pub = rospy.Publisher('/amcl_pose', PoseWithCovarianceStamped, queue_size=1)
        
        # Publisher for robot odometry (based on GNSS position)
        self.odom_pub = rospy.Publisher('/odom', Odometry, queue_size=1)
        
        # Subscribe to real robot GNSS data
        self.gps_sub = rospy.Subscriber('/gps/fix', NavSatFix, self.gps_callback)
        self.utm_local_sub = rospy.Subscriber('/utm_local', PoseStamped, self.utm_local_callback)
        self.imu_sub = rospy.Subscriber('/imu', Imu, self.imu_callback)
        
        # Subscribe to map switch status to handle TF recovery
        self.map_switch_sub = rospy.Subscriber('/robot/map_switch_status', String, self.map_switch_callback)
        
        # Initialize coordinate transformers
        self.setup_coordinate_transformer()
        
        # Robot position and orientation (UTM coordinates)
        # Will be initialized from GPS data when available
        self.x = None  # UTM X coordinate (from GPS)
        self.y = None  # UTM Y coordinate (from GPS)
        self.z = 0.0  # Z coordinate (from GPS altitude or IMU)
        self.theta = 0.0  # Orientation in radians (from utm_local or IMU)
        
        # Full orientation quaternion from IMU
        self.orientation_x = 0.0
        self.orientation_y = 0.0
        self.orientation_z = 0.0
        self.orientation_w = 1.0
        
        # Velocity tracking for odometry
        self.last_x = None
        self.last_y = None
        self.last_time = None
        self.current_fix_time = None
        
        # Data validity flags
        self.has_gps_data = False
        self.has_orientation_data = False
        self.has_imu_data = False
        
        # TF recovery and timing management
        self.map_switching = False
        self.force_tf_publish = False
        self.tf_recovery_count = 0
        self.last_tf_time = rospy.Time.now()
        
        # Timer for publishing - use high frequency for robust TF
        rospy.Timer(rospy.Duration(0.05), self.publish_pose)  # 20 Hz for robust TF
        
        # TF monitoring and recovery timer
        rospy.Timer(rospy.Duration(0.1), self.tf_health_monitor)  # 10 Hz monitoring
        
        rospy.loginfo("GNSS localization node started")
        rospy.loginfo("Subscribing to: /gps/fix, /utm_local, /imu")
        rospy.loginfo("Publishing to: /amcl_pose, /odom, TF transforms")
        rospy.loginfo("TF recovery system active - monitoring for timing issues")
        
    def setup_coordinate_transformer(self):
        """Initialize PyProj coordinate transformers"""
        try:
            self.crs_wgs84 = pyproj.CRS('EPSG:4326')
            self.crs_utm32 = pyproj.CRS('EPSG:25832')
            self.wgs84_to_utm = pyproj.Transformer.from_crs(self.crs_wgs84, self.crs_utm32, always_xy=True)
            rospy.loginfo("Coordinate transformers ready (WGS84 → UTM32N)")
        except Exception as e:
            rospy.logerr(f"Coordinate transformer init failed: {e}")
            self.wgs84_to_utm = None

    def wgs84_to_utm_xy(self, lon, lat):
        """Convert WGS84 lon/lat to UTM32 x/y"""
        if self.wgs84_to_utm is None:
            raise ValueError("Transformer not initialized")
        x, y = self.wgs84_to_utm.transform(lon, lat)
        return x, y
        
    def gps_callback(self, msg):
        """Handle GPS fix data (WGS84 coordinates)"""
        try:
            if msg.status.status >= 0:  # Valid GPS fix
                # Get current timestamp for this fix
                current_fix_time = rospy.Time.now()
                
                # Store previous position and timestamp for velocity calculation
                if self.x is not None and self.current_fix_time is not None:
                    self.last_x = self.x
                    self.last_y = self.y
                    self.last_time = self.current_fix_time  # Use timestamp of previous fix
                
                # Update current fix timestamp
                self.current_fix_time = current_fix_time
                
                # Convert WGS84 to UTM coordinates
                utm_x, utm_y = self.wgs84_to_utm_xy(msg.longitude, msg.latitude)
                
                self.x = utm_x
                self.y = utm_y
                self.z = msg.altitude if hasattr(msg, 'altitude') else 0.0  # Use GPS altitude if available
                self.has_gps_data = True
                
                rospy.logdebug(f"GPS position: WGS84({msg.longitude:.6f}, {msg.latitude:.6f}) → UTM({utm_x:.3f}, {utm_y:.3f}, {self.z:.3f})")
                
                # Force TF update when we get new GPS data
                self.force_tf_publish = True
                
        except Exception as e:
            rospy.logerr(f"Error processing GPS data: {e}")
            self.has_gps_data = False
    
    def utm_local_callback(self, msg):
        """Handle UTM local orientation data"""
        try:
            # Extract yaw from PoseStamped orientation quaternion
            qx = msg.pose.orientation.x
            qy = msg.pose.orientation.y
            qz = msg.pose.orientation.z
            qw = msg.pose.orientation.w
            
            # Calculate yaw (rotation around Z-axis) - full formula for any roll/pitch
            self.theta = math.atan2(2.0 * (qw * qz + qx * qy), 1.0 - 2.0 * (qy * qy + qz * qz))
            
            # Normalize angle to [-pi, pi]
            while self.theta > math.pi:
                self.theta -= 2 * math.pi
            while self.theta < -math.pi:
                self.theta += 2 * math.pi
            
            # Store full quaternion for TF publishing
            self.orientation_x = qx
            self.orientation_y = qy
            self.orientation_z = qz
            self.orientation_w = qw
            
            self.has_orientation_data = True
            rospy.logdebug(f"UTM local orientation: yaw={self.theta:.3f} rad, quaternion=({qx:.3f}, {qy:.3f}, {qz:.3f}, {qw:.3f})")
                
        except Exception as e:
            rospy.logerr(f"Error processing UTM local data: {e}")
            self.has_orientation_data = False
    
    def imu_callback(self, msg):
        """Handle IMU data for additional orientation information"""
        try:
            # Store full quaternion orientation from IMU
            self.orientation_x = msg.orientation.x
            self.orientation_y = msg.orientation.y
            self.orientation_z = msg.orientation.z
            self.orientation_w = msg.orientation.w
            
            # Extract yaw from IMU quaternion if utm_local is not available
            if not self.has_orientation_data:
                # Convert quaternion to euler angles
                qx, qy, qz, qw = msg.orientation.x, msg.orientation.y, msg.orientation.z, msg.orientation.w
                
                # Calculate yaw (rotation around Z-axis)
                self.theta = math.atan2(2.0 * (qw * qz + qx * qy), 1.0 - 2.0 * (qy * qy + qz * qz))
                
                # Normalize angle to [-pi, pi]
                while self.theta > math.pi:
                    self.theta -= 2 * math.pi
                while self.theta < -math.pi:
                    self.theta += 2 * math.pi
            
            self.has_imu_data = True
            rospy.logdebug(f"IMU orientation: yaw={self.theta:.3f} rad, quaternion=({qx:.3f}, {qy:.3f}, {qz:.3f}, {qw:.3f})")
                
        except Exception as e:
            rospy.logerr(f"Error processing IMU data: {e}")
            self.has_imu_data = False
    
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
            
    def calculate_velocities(self):
        """Calculate velocities from position changes"""
        # Guard against None values to prevent TypeError
        if (self.last_x is not None and self.last_y is not None and 
            self.last_time is not None and self.current_fix_time is not None and
            self.x is not None and self.y is not None):
            
            # Use the actual time between GPS fixes
            dt = (self.current_fix_time - self.last_time).to_sec()
            
            if dt > 0.0 and dt < 10.0:  # Reasonable time delta
                dx = self.x - self.last_x
                dy = self.y - self.last_y
                
                linear_x = dx / dt
                linear_y = dy / dt
                
                return linear_x, linear_y, 0.0  # angular_z = 0 for now
            else:
                return 0.0, 0.0, 0.0
        else:
            return 0.0, 0.0, 0.0
    
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
        
    def publish_pose(self, event):
        current_time = rospy.Time.now()
        
        # Check if we have valid data
        if not self.has_gps_data or self.x is None or self.y is None:
            rospy.logwarn_throttle(5, "No GPS data available - cannot publish pose")
            return
        
        if not (self.has_orientation_data or self.has_imu_data):
            rospy.logwarn_throttle(5, "No orientation data available - using default orientation")
            self.theta = 0.0  # Default orientation
        
        # Publish transform from map to base_link directly
        t = TransformStamped()
        t.header.stamp = current_time
        t.header.frame_id = "map"
        t.child_frame_id = "base_link"
        t.transform.translation.x = self.x  # Robot position in map (UTM coordinates)
        t.transform.translation.y = self.y
        t.transform.translation.z = self.z  # Real Z position from GPS altitude
        t.transform.rotation.x = self.orientation_x  # Real orientation from IMU
        t.transform.rotation.y = self.orientation_y
        t.transform.rotation.z = self.orientation_z
        t.transform.rotation.w = self.orientation_w
        
        # Send transform
        try:
            self.tf_broadcaster.sendTransform(t)
            self.last_tf_time = current_time
            
            # Reset force flag after successful publish
            if self.force_tf_publish:
                self.force_tf_publish = False
                
        except Exception as e:
            rospy.logerr("Failed to publish TF transform: %s", str(e))
            # Retry on next cycle
            return
        
        # Publish robot pose in map frame (AMCL format)
        pose_msg = PoseWithCovarianceStamped()
        pose_msg.header.stamp = current_time
        pose_msg.header.frame_id = "map"
        pose_msg.pose.pose.position.x = self.x
        pose_msg.pose.pose.position.y = self.y
        pose_msg.pose.pose.position.z = self.z  # Real Z position from GPS altitude
        pose_msg.pose.pose.orientation.x = self.orientation_x  # Real orientation from IMU
        pose_msg.pose.pose.orientation.y = self.orientation_y
        pose_msg.pose.pose.orientation.z = self.orientation_z
        pose_msg.pose.pose.orientation.w = self.orientation_w
        
        # Set covariance (small values indicating good localization)
        pose_msg.pose.covariance = [0.1, 0.0, 0.0, 0.0, 0.0, 0.0,
                                   0.0, 0.1, 0.0, 0.0, 0.0, 0.0,
                                   0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                                   0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                                   0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                                   0.0, 0.0, 0.0, 0.0, 0.0, 0.1]
        
        self.pose_pub.publish(pose_msg)
        
        # Publish robot odometry (based on GNSS position)
        # Since we're publishing map → base_link directly, odometry is relative to map
        odom_msg = Odometry()
        odom_msg.header.stamp = current_time
        odom_msg.header.frame_id = "map"  # Changed from "odom" to "map"
        odom_msg.child_frame_id = "base_link"
        odom_msg.pose.pose.position.x = self.x  # Robot position in map frame
        odom_msg.pose.pose.position.y = self.y
        odom_msg.pose.pose.position.z = self.z
        odom_msg.pose.pose.orientation.x = self.orientation_x
        odom_msg.pose.pose.orientation.y = self.orientation_y
        odom_msg.pose.pose.orientation.z = self.orientation_z
        odom_msg.pose.pose.orientation.w = self.orientation_w
        
        # Calculate real velocities from position changes
        linear_x, linear_y, angular_z = self.calculate_velocities()
        odom_msg.twist.twist.linear.x = linear_x
        odom_msg.twist.twist.linear.y = linear_y
        odom_msg.twist.twist.angular.z = angular_z
        
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
        localization = GNSSLocalization()
        rospy.spin()
    except rospy.ROSInterruptException:
        pass 