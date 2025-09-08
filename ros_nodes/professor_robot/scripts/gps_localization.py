#!/usr/bin/env python

import rospy
import tf2_ros
import yaml
import math
import os
from sensor_msgs.msg import NavSatFix
from geometry_msgs.msg import PoseWithCovarianceStamped, TransformStamped, Twist
from nav_msgs.msg import Odometry
from std_msgs.msg import String
import pyproj

class GpsLocalization:
    """
    GPS-based localization for real robot deployment
    
    Replaces fake_localization.py with real GPS coordinate processing:
    - Subscribes to /fix topic (sensor_msgs/NavSatFix) for GPS data
    - Transforms WGS84 (lat/lon) → EPSG:25832 (German UTM Zone 32N) → Map Frame
    - Maintains same interface as fake_localization for navigation stack compatibility
    - Handles dynamic map origin updates when maps change
    - Publishes /amcl_pose and /odom for navigation stack
    - Broadcasts TF transforms: map → odom → base_link
    """
    
    def __init__(self):
        rospy.init_node('gps_localization')
        
        # ROS Parameters
        self.gps_topic = rospy.get_param('~gps_topic', '/fix')
        self.coordinate_frame = rospy.get_param('~coordinate_frame', 'EPSG:25832')
        self.map_frame = rospy.get_param('~map_frame', 'map')
        self.odom_frame = rospy.get_param('~odom_frame', 'odom')
        self.base_frame = rospy.get_param('~base_frame', 'base_link')
        
        rospy.loginfo("🛰️ GPS Localization Node Starting...")
        rospy.loginfo(f"   GPS Topic: {self.gps_topic}")
        rospy.loginfo(f"   Coordinate Frame: {self.coordinate_frame}")
        rospy.loginfo(f"   Map Frame: {self.map_frame}")
        
        # Initialize TF broadcaster
        self.tf_broadcaster = tf2_ros.TransformBroadcaster()
        
        # GPS and position tracking
        self.last_gps_fix = None
        self.current_position = [0.0, 0.0, 0.0]  # x, y, theta in map frame
        self.gps_accuracy = 2.0  # Default GPS accuracy in meters
        self.position_initialized = False
        
        # Map origin management
        self.map_origin = [0.0, 0.0, 0.0]  # Default map origin
        self.current_map_id = None
        
        # Setup coordinate transformers
        self.setup_coordinate_transformers()
        
        # ROS Publishers (same interface as fake_localization)
        self.pose_pub = rospy.Publisher('/amcl_pose', PoseWithCovarianceStamped, queue_size=1)
        self.odom_pub = rospy.Publisher('/odom', Odometry, queue_size=1)
        
        # ROS Subscribers
        self.gps_sub = rospy.Subscriber(self.gps_topic, NavSatFix, self.gps_callback)
        self.map_sub = rospy.Subscriber('/robot/map_switch_status', String, self.map_callback)
        
        # Publishing timer
        self.timer = rospy.Timer(rospy.Duration(0.1), self.publish_transforms)  # 10Hz
        
        rospy.loginfo("✅ GPS Localization Node initialized successfully")
        rospy.loginfo("   Waiting for GPS fix on topic: {}".format(self.gps_topic))
    
    def setup_coordinate_transformers(self):
        """Initialize coordinate transformation objects using pyproj"""
        try:
            # Define coordinate systems
            self.wgs84 = pyproj.CRS('EPSG:4326')      # GPS lat/lon (WGS84)
            self.utm32 = pyproj.CRS('EPSG:25832')     # German UTM Zone 32N
            
            # Create bidirectional transformers
            self.wgs84_to_utm = pyproj.Transformer.from_crs(
                self.wgs84, self.utm32, always_xy=True
            )
            self.utm_to_wgs84 = pyproj.Transformer.from_crs(
                self.utm32, self.wgs84, always_xy=True
            )
            
            rospy.loginfo("🔄 Coordinate transformers initialized successfully")
            rospy.loginfo("   WGS84 (GPS) ↔ EPSG:25832 (German UTM Zone 32N)")
            
        except Exception as e:
            rospy.logerr(f"❌ Failed to initialize coordinate transformers: {e}")
            rospy.signal_shutdown("Coordinate transformer initialization failed")
    
    def gps_callback(self, msg):
        """Process GPS fix messages and update robot position"""
        try:
            # Check GPS fix quality
            if msg.status.status < 0:  # No fix
                rospy.logwarn_throttle(5.0, "⚠️ GPS: No fix available")
                return
            
            # Store GPS data
            self.last_gps_fix = msg
            lat, lon = msg.latitude, msg.longitude
            altitude = msg.altitude
            
            # Update GPS accuracy from covariance if available
            if len(msg.position_covariance) >= 9:
                # Use horizontal accuracy (x and y variance)
                x_var = msg.position_covariance[0]
                y_var = msg.position_covariance[4]
                self.gps_accuracy = math.sqrt((x_var + y_var) / 2.0)
            
            # Transform GPS coordinates to map frame
            x_map, y_map = self.gps_to_map_frame(lat, lon)
            
            # Update current position
            self.current_position[0] = x_map
            self.current_position[1] = y_map
            # Note: GPS doesn't provide orientation, keeping last theta
            
            if not self.position_initialized:
                rospy.loginfo(f"🎯 GPS position initialized: ({x_map:.3f}, {y_map:.3f})")
                rospy.loginfo(f"   GPS coordinates: ({lat:.6f}, {lon:.6f})")
                rospy.loginfo(f"   GPS accuracy: {self.gps_accuracy:.2f}m")
                self.position_initialized = True
            
            # Publish robot pose and odometry
            self.publish_robot_pose(x_map, y_map, altitude)
            
        except Exception as e:
            rospy.logerr(f"❌ Error processing GPS fix: {e}")
    
    def gps_to_map_frame(self, lat, lon):
        """Convert GPS coordinates to map frame position"""
        try:
            # Step 1: Transform WGS84 → UTM
            x_utm, y_utm = self.wgs84_to_utm.transform(lon, lat)
            
            # Step 2: Transform UTM → Map Frame (subtract map origin)
            x_map = x_utm - self.map_origin[0]
            y_map = y_utm - self.map_origin[1]
            
            rospy.logdebug(f"🔄 Coordinate transform: GPS({lat:.6f}, {lon:.6f}) → UTM({x_utm:.3f}, {y_utm:.3f}) → Map({x_map:.3f}, {y_map:.3f})")
            
            return x_map, y_map
            
        except Exception as e:
            rospy.logerr(f"❌ Coordinate transformation failed: {e}")
            return 0.0, 0.0
    
    def map_callback(self, msg):
        """Handle map switch notifications and update map origin"""
        try:
            if msg.data.startswith("SUCCESS:"):
                map_id = msg.data.split(":")[1].strip()
                rospy.loginfo(f"🗺️ Map switch detected: {map_id}")
                
                # Load new map origin
                if self.load_map_origin(map_id):
                    self.current_map_id = map_id
                    rospy.loginfo(f"✅ Map origin updated for GPS localization")
                    
                    # Re-calculate position with new map origin if GPS is available
                    if self.last_gps_fix:
                        lat, lon = self.last_gps_fix.latitude, self.last_gps_fix.longitude
                        x_map, y_map = self.gps_to_map_frame(lat, lon)
                        self.current_position[0] = x_map
                        self.current_position[1] = y_map
                        rospy.loginfo(f"📍 Position updated for new map: ({x_map:.3f}, {y_map:.3f})")
                
        except Exception as e:
            rospy.logerr(f"❌ Error handling map switch: {e}")
    
    def load_map_origin(self, map_id):
        """Load map origin from map.yaml file"""
        try:
            map_yaml_path = f"/tmp/fiware_maps/{map_id}/map.yaml"
            
            if not os.path.exists(map_yaml_path):
                rospy.logwarn(f"⚠️ Map YAML not found: {map_yaml_path}")
                return False
            
            with open(map_yaml_path, 'r') as f:
                map_config = yaml.safe_load(f)
                
            # Extract origin coordinates
            new_origin = map_config.get('origin', [0.0, 0.0, 0.0])
            
            rospy.loginfo(f"🗺️ Map origin loaded: {new_origin}")
            rospy.loginfo(f"   Previous origin: {self.map_origin}")
            
            self.map_origin = new_origin
            return True
            
        except Exception as e:
            rospy.logerr(f"❌ Failed to load map origin: {e}")
            return False
    
    def publish_robot_pose(self, x_map, y_map, altitude=0.0):
        """Publish robot pose for navigation stack"""
        try:
            current_time = rospy.Time.now()
            
            # Create pose message for move_base (same as fake_localization interface)
            pose_msg = PoseWithCovarianceStamped()
            pose_msg.header.stamp = current_time
            pose_msg.header.frame_id = self.map_frame
            
            # Set position
            pose_msg.pose.pose.position.x = x_map
            pose_msg.pose.pose.position.y = y_map
            pose_msg.pose.pose.position.z = 0.0  # 2D navigation
            
            # Set orientation (quaternion from theta)
            theta = self.current_position[2]
            pose_msg.pose.pose.orientation.x = 0.0
            pose_msg.pose.pose.orientation.y = 0.0
            pose_msg.pose.pose.orientation.z = math.sin(theta / 2.0)
            pose_msg.pose.pose.orientation.w = math.cos(theta / 2.0)
            
            # Set covariance based on GPS accuracy
            pose_msg.pose.covariance[0] = self.gps_accuracy * self.gps_accuracy   # x variance
            pose_msg.pose.covariance[7] = self.gps_accuracy * self.gps_accuracy   # y variance
            pose_msg.pose.covariance[35] = 0.1 * 0.1  # theta variance (GPS doesn't provide orientation)
            
            # Publish pose
            self.pose_pub.publish(pose_msg)
            
            # Create and publish odometry message
            odom_msg = Odometry()
            odom_msg.header.stamp = current_time
            odom_msg.header.frame_id = self.odom_frame
            odom_msg.child_frame_id = self.base_frame
            
            # Copy pose data
            odom_msg.pose = pose_msg.pose
            
            # Velocity is zero (GPS doesn't provide velocity directly)
            odom_msg.twist.twist.linear.x = 0.0
            odom_msg.twist.twist.linear.y = 0.0
            odom_msg.twist.twist.angular.z = 0.0
            
            # Publish odometry
            self.odom_pub.publish(odom_msg)
            
        except Exception as e:
            rospy.logerr(f"❌ Error publishing robot pose: {e}")
    
    def publish_transforms(self, event):
        """Publish TF transforms: map → odom → base_link"""
        try:
            if not self.position_initialized:
                return
            
            current_time = rospy.Time.now()
            
            # Publish map → odom transform
            map_to_odom = TransformStamped()
            map_to_odom.header.stamp = current_time
            map_to_odom.header.frame_id = self.map_frame
            map_to_odom.child_frame_id = self.odom_frame
            
            # GPS position in map frame
            map_to_odom.transform.translation.x = self.current_position[0]
            map_to_odom.transform.translation.y = self.current_position[1]
            map_to_odom.transform.translation.z = 0.0
            
            # Orientation from theta
            theta = self.current_position[2]
            map_to_odom.transform.rotation.x = 0.0
            map_to_odom.transform.rotation.y = 0.0
            map_to_odom.transform.rotation.z = math.sin(theta / 2.0)
            map_to_odom.transform.rotation.w = math.cos(theta / 2.0)
            
            # Publish odom → base_link transform
            odom_to_base = TransformStamped()
            odom_to_base.header.stamp = current_time
            odom_to_base.header.frame_id = self.odom_frame
            odom_to_base.child_frame_id = self.base_frame
            
            # Identity transform (robot at origin of odom frame)
            odom_to_base.transform.translation.x = 0.0
            odom_to_base.transform.translation.y = 0.0
            odom_to_base.transform.translation.z = 0.0
            odom_to_base.transform.rotation.x = 0.0
            odom_to_base.transform.rotation.y = 0.0
            odom_to_base.transform.rotation.z = 0.0
            odom_to_base.transform.rotation.w = 1.0
            
            # Broadcast transforms
            self.tf_broadcaster.sendTransform([map_to_odom, odom_to_base])
            
        except Exception as e:
            rospy.logerr(f"❌ Error publishing TF transforms: {e}")

if __name__ == '__main__':
    try:
        gps_localization = GpsLocalization()
        rospy.spin()
    except rospy.ROSInterruptException:
        rospy.loginfo("🛰️ GPS Localization Node shutting down")
    except Exception as e:
        rospy.logerr(f"❌ GPS Localization Node error: {e}") 