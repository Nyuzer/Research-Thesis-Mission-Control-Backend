#!/usr/bin/env python

import rospy
import tf2_ros
import yaml
import math
import os
import threading
from collections import deque
import numpy as np
from sensor_msgs.msg import NavSatFix
from geometry_msgs.msg import PoseWithCovarianceStamped, TransformStamped, Twist
from nav_msgs.msg import Odometry
from std_msgs.msg import String
import pyproj

class EnhancedGpsLocalization:
    """
    Enhanced GPS-based localization with accuracy improvements:
    
    Features:
    - GPS signal quality monitoring and adaptive filtering
    - Position smoothing and outlier rejection
    - Dynamic covariance adjustment based on GPS quality
    - Multi-rate processing (GPS at 1-10Hz, output at 30Hz)
    - Integration with robot_localization EKF
    - Coordinate transformation accuracy validation
    """
    
    def __init__(self):
        rospy.init_node('enhanced_gps_localization')
        
        # ROS Parameters
        self.gps_topic = rospy.get_param('~gps_topic', '/fix')
        self.coordinate_frame = rospy.get_param('~coordinate_frame', 'EPSG:25832')
        self.map_frame = rospy.get_param('~map_frame', 'map')
        self.odom_frame = rospy.get_param('~odom_frame', 'odom')
        self.base_frame = rospy.get_param('~base_frame', 'base_link')
        
        # Enhanced GPS parameters
        self.min_satellites = rospy.get_param('~min_satellites', 6)
        self.max_position_jump = rospy.get_param('~max_position_jump', 10.0)  # meters
        self.gps_buffer_size = rospy.get_param('~gps_buffer_size', 10)
        self.output_frequency = rospy.get_param('~output_frequency', 30.0)  # Hz
        
        rospy.loginfo("🛰️ Enhanced GPS Localization Node Starting...")
        rospy.loginfo(f"   GPS Topic: {self.gps_topic}")
        rospy.loginfo(f"   Output Frequency: {self.output_frequency} Hz")
        rospy.loginfo(f"   Min Satellites: {self.min_satellites}")
        rospy.loginfo(f"   Max Position Jump: {self.max_position_jump}m")
        
        # Initialize TF broadcaster
        self.tf_broadcaster = tf2_ros.TransformBroadcaster()
        
        # GPS processing state
        self.last_gps_fix = None
        self.current_position = [0.0, 0.0, 0.0]  # x, y, theta in map frame
        self.position_initialized = False
        self.gps_quality = 0.0
        self.last_position_time = rospy.Time.now()
        
        # GPS buffer for smoothing
        self.gps_buffer = deque(maxlen=self.gps_buffer_size)
        self.buffer_lock = threading.Lock()
        
        # Map origin management  
        self.map_origin = [0.0, 0.0, 0.0]
        self.current_map_id = None
        
        # Setup coordinate transformers
        self.setup_coordinate_transformers()
        
        # ROS Publishers - compatible with robot_localization
        self.pose_pub = rospy.Publisher('/amcl_pose', PoseWithCovarianceStamped, queue_size=1)
        self.odom_pub = rospy.Publisher('/odometry/gps', Odometry, queue_size=1)  # For robot_localization
        self.quality_pub = rospy.Publisher('/gps_quality', String, queue_size=1)
        
        # ROS Subscribers
        self.gps_sub = rospy.Subscriber(self.gps_topic, NavSatFix, self.gps_callback)
        self.map_sub = rospy.Subscriber('/robot/map_switch_status', String, self.map_callback)
        
        # High-frequency output timer
        self.output_timer = rospy.Timer(
            rospy.Duration(1.0 / self.output_frequency), 
            self.publish_filtered_pose
        )
        
        rospy.loginfo("✅ Enhanced GPS Localization Node initialized")
        rospy.loginfo("   GPS quality monitoring active")
        rospy.loginfo("   Position smoothing enabled")
    
    def setup_coordinate_transformers(self):
        """Initialize high-precision coordinate transformation objects"""
        try:
            # Define coordinate systems with area of interest for better accuracy
            self.wgs84 = pyproj.CRS('EPSG:4326')
            self.utm32 = pyproj.CRS('EPSG:25832')
            
            # Create transformer optimized for German region
            self.wgs84_to_utm = pyproj.Transformer.from_crs(
                self.wgs84, self.utm32,
                always_xy=True,
                accuracy=1.0,  # 1 meter accuracy requirement
                area_of_interest=pyproj.aoi.AreaOfInterest(
                    west_lon_degree=6.0,   # Germany bounds
                    south_lat_degree=50.0,
                    east_lon_degree=9.0,
                    north_lat_degree=53.0
                )
            )
            
            # Reverse transformer for validation
            self.utm_to_wgs84 = pyproj.Transformer.from_crs(
                self.utm32, self.wgs84,
                always_xy=True,
                accuracy=1.0,
                area_of_interest=pyproj.aoi.AreaOfInterest(
                    west_lon_degree=6.0,
                    south_lat_degree=50.0,
                    east_lon_degree=9.0,
                    north_lat_degree=53.0
                )
            )
            
            rospy.loginfo("🔄 High-precision coordinate transformers initialized")
            rospy.loginfo("   Optimized for German UTM Zone 32N region")
            
        except Exception as e:
            rospy.logerr(f"❌ Failed to initialize coordinate transformers: {e}")
            rospy.signal_shutdown("Coordinate transformer initialization failed")
    
    def assess_gps_quality(self, msg):
        """Comprehensive GPS signal quality assessment"""
        quality_factors = []
        
        # Factor 1: GPS fix status
        if msg.status.status >= 0:  # Valid fix
            fix_quality = 1.0
        elif msg.status.status >= -1:  # GPS fix but accuracy unknown
            fix_quality = 0.7
        else:  # No fix
            fix_quality = 0.0
        quality_factors.append(fix_quality)
        
        # Factor 2: Position accuracy (from covariance)
        if len(msg.position_covariance) >= 9:
            horizontal_accuracy = math.sqrt(
                msg.position_covariance[0] + msg.position_covariance[4]
            )
            # Convert accuracy to quality score (0-1)
            # 1m accuracy = 1.0, 10m accuracy = 0.0
            accuracy_quality = max(0.0, 1.0 - (horizontal_accuracy - 1.0) / 9.0)
            quality_factors.append(accuracy_quality)
        
        # Factor 3: Satellite count (if available in status service)
        # Note: NavSatFix doesn't include satellite count by default
        # This would need additional GPS driver that publishes satellite info
        
        # Factor 4: Position consistency check
        if len(self.gps_buffer) >= 2:
            # Check if current position is consistent with recent positions
            lat, lon = msg.latitude, msg.longitude
            try:
                x_utm, y_utm = self.wgs84_to_utm.transform(lon, lat)
                
                # Compare with recent GPS positions
                recent_positions = list(self.gps_buffer)[-3:]  # Last 3 readings
                position_consistency = 1.0
                
                for recent_gps in recent_positions:
                    recent_x, recent_y = recent_gps['utm_position']
                    distance = math.sqrt((x_utm - recent_x)**2 + (y_utm - recent_y)**2)
                    
                    # Large jumps reduce consistency score
                    if distance > self.max_position_jump:
                        position_consistency *= 0.1  # Severe penalty for jumps
                    elif distance > 5.0:
                        position_consistency *= 0.5  # Moderate penalty
                
                quality_factors.append(position_consistency)
                
            except Exception:
                quality_factors.append(0.5)  # Neutral if calculation fails
        
        # Calculate overall quality score
        if quality_factors:
            overall_quality = sum(quality_factors) / len(quality_factors)
        else:
            overall_quality = 0.0
        
        return overall_quality
    
    def validate_coordinate_transformation(self, lat, lon):
        """Validate coordinate transformation accuracy"""
        try:
            # Forward transformation
            x_utm, y_utm = self.wgs84_to_utm.transform(lon, lat)
            
            # Reverse check for accuracy validation
            lon_check, lat_check = self.utm_to_wgs84.transform(x_utm, y_utm)
            
            # Calculate transformation error
            lat_error = abs(lat - lat_check)
            lon_error = abs(lon - lon_check)
            
            # Convert to meters for error assessment
            lat_error_m = lat_error * 111000  # Rough degrees to meters
            lon_error_m = lon_error * 111000 * math.cos(math.radians(lat))
            
            total_error_m = math.sqrt(lat_error_m**2 + lon_error_m**2)
            
            # Warn if transformation error is significant
            if total_error_m > 1.0:  # >1m transformation error
                rospy.logwarn(f"⚠️ Coordinate transformation error: {total_error_m:.2f}m")
                return False, total_error_m
            
            return True, total_error_m
            
        except Exception as e:
            rospy.logerr(f"❌ Coordinate transformation validation failed: {e}")
            return False, float('inf')
    
    def gps_callback(self, msg):
        """Enhanced GPS processing with quality monitoring"""
        try:
            # Assess GPS signal quality
            gps_quality = self.assess_gps_quality(msg)
            self.gps_quality = gps_quality
            
            # Reject poor quality GPS readings
            if gps_quality < 0.3:
                rospy.logwarn_throttle(5.0, f"⚠️ GPS quality too low ({gps_quality:.2f}) - rejecting reading")
                return
            
            lat, lon = msg.latitude, msg.longitude
            altitude = msg.altitude
            
            # Validate coordinate transformation
            transform_valid, transform_error = self.validate_coordinate_transformation(lat, lon)
            if not transform_valid:
                rospy.logwarn(f"⚠️ GPS coordinate transformation error too large: {transform_error:.2f}m")
                return
            
            # Transform coordinates
            x_utm, y_utm = self.wgs84_to_utm.transform(lon, lat)
            x_map, y_map = self.gps_to_map_frame(lat, lon)
            
            # Calculate GPS accuracy from covariance
            gps_accuracy = 5.0  # Default
            if len(msg.position_covariance) >= 9:
                x_var = msg.position_covariance[0]
                y_var = msg.position_covariance[4]
                gps_accuracy = math.sqrt((x_var + y_var) / 2.0)
            
            # Store GPS reading in buffer with quality weighting
            gps_reading = {
                'timestamp': rospy.Time.now(),
                'wgs84_position': [lat, lon, altitude],
                'utm_position': [x_utm, y_utm],
                'map_position': [x_map, y_map],
                'accuracy': gps_accuracy,
                'quality': gps_quality,
                'covariance': msg.position_covariance
            }
            
            with self.buffer_lock:
                self.gps_buffer.append(gps_reading)
            
            # Update current position with quality-weighted average
            self.update_filtered_position()
            
            # Store latest GPS fix
            self.last_gps_fix = msg
            
            if not self.position_initialized:
                rospy.loginfo(f"🎯 Enhanced GPS position initialized:")
                rospy.loginfo(f"   Map coordinates: ({x_map:.3f}, {y_map:.3f})")
                rospy.loginfo(f"   GPS accuracy: {gps_accuracy:.2f}m")
                rospy.loginfo(f"   Signal quality: {gps_quality:.2f}")
                self.position_initialized = True
            
            # Publish GPS quality information
            quality_msg = String()
            quality_msg.data = f"quality:{gps_quality:.2f},accuracy:{gps_accuracy:.2f},error:{transform_error:.2f}"
            self.quality_pub.publish(quality_msg)
            
        except Exception as e:
            rospy.logerr(f"❌ Error in enhanced GPS processing: {e}")
    
    def update_filtered_position(self):
        """Update current position using quality-weighted filtering"""
        with self.buffer_lock:
            if len(self.gps_buffer) == 0:
                return
            
            # Get recent GPS readings (last 5)
            recent_readings = list(self.gps_buffer)[-5:]
            
            # Calculate quality-weighted average position
            total_weight = 0.0
            weighted_x = 0.0
            weighted_y = 0.0
            
            for reading in recent_readings:
                # Weight by quality and recency
                age = (rospy.Time.now() - reading['timestamp']).to_sec()
                age_weight = max(0.1, 1.0 - age / 10.0)  # Reduce weight with age
                
                total_weight_for_reading = reading['quality'] * age_weight
                
                weighted_x += reading['map_position'][0] * total_weight_for_reading
                weighted_y += reading['map_position'][1] * total_weight_for_reading
                total_weight += total_weight_for_reading
            
            if total_weight > 0:
                self.current_position[0] = weighted_x / total_weight
                self.current_position[1] = weighted_y / total_weight
                self.last_position_time = rospy.Time.now()
    
    def publish_filtered_pose(self, event):
        """Publish high-frequency filtered pose for navigation stack"""
        if not self.position_initialized:
            return
        
        current_time = rospy.Time.now()
        
        # Calculate dynamic covariance based on GPS quality
        base_covariance = 5.0  # Base uncertainty in meters
        quality_factor = max(0.1, self.gps_quality)
        position_covariance = (base_covariance / quality_factor) ** 2
        
        # Publish GPS odometry for robot_localization EKF
        gps_odom = Odometry()
        gps_odom.header.stamp = current_time
        gps_odom.header.frame_id = self.odom_frame
        gps_odom.child_frame_id = self.base_frame
        
        # Position
        gps_odom.pose.pose.position.x = self.current_position[0]
        gps_odom.pose.pose.position.y = self.current_position[1]
        gps_odom.pose.pose.position.z = 0.0
        
        # Orientation (unknown from GPS)
        gps_odom.pose.pose.orientation.w = 1.0
        
        # Dynamic covariance based on GPS quality
        gps_odom.pose.covariance[0] = position_covariance   # x variance
        gps_odom.pose.covariance[7] = position_covariance   # y variance
        gps_odom.pose.covariance[14] = 999999.0             # z variance (unused)
        gps_odom.pose.covariance[21] = 999999.0             # roll variance (unused)
        gps_odom.pose.covariance[28] = 999999.0             # pitch variance (unused)
        gps_odom.pose.covariance[35] = 999999.0             # yaw variance (unknown)
        
        self.odom_pub.publish(gps_odom)
        
        # Also publish AMCL pose for compatibility
        pose_msg = PoseWithCovarianceStamped()
        pose_msg.header = gps_odom.header
        pose_msg.header.frame_id = self.map_frame
        pose_msg.pose = gps_odom.pose
        self.pose_pub.publish(pose_msg)
    
    def gps_to_map_frame(self, lat, lon):
        """Convert GPS coordinates to map frame position"""
        try:
            # Transform WGS84 → UTM
            x_utm, y_utm = self.wgs84_to_utm.transform(lon, lat)
            
            # Transform UTM → Map Frame (subtract map origin)
            x_map = x_utm - self.map_origin[0]
            y_map = y_utm - self.map_origin[1]
            
            return x_map, y_map
            
        except Exception as e:
            rospy.logerr(f"❌ GPS to map frame transformation failed: {e}")
            return 0.0, 0.0
    
    def map_callback(self, msg):
        """Handle map switch notifications and update map origin"""
        try:
            if msg.data.startswith("SUCCESS:"):
                map_id = msg.data.split(":")[1].strip()
                rospy.loginfo(f"🗺️ Map switch detected: {map_id}")
                
                if self.load_map_origin(map_id):
                    self.current_map_id = map_id
                    rospy.loginfo(f"✅ Map origin updated for enhanced GPS localization")
                    
                    # Recalculate all positions in buffer for new map
                    with self.buffer_lock:
                        for reading in self.gps_buffer:
                            lat, lon = reading['wgs84_position'][:2]
                            x_map, y_map = self.gps_to_map_frame(lat, lon)
                            reading['map_position'] = [x_map, y_map]
                    
                    # Update current position
                    self.update_filtered_position()
                
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
                
            new_origin = map_config.get('origin', [0.0, 0.0, 0.0])
            
            rospy.loginfo(f"🗺️ Map origin loaded: {new_origin}")
            rospy.loginfo(f"   Previous origin: {self.map_origin}")
            
            self.map_origin = new_origin
            return True
            
        except Exception as e:
            rospy.logerr(f"❌ Failed to load map origin: {e}")
            return False

if __name__ == '__main__':
    try:
        enhanced_gps = EnhancedGpsLocalization()
        rospy.spin()
    except rospy.ROSInterruptException:
        rospy.loginfo("🛰️ Enhanced GPS Localization Node shutting down")
    except Exception as e:
        rospy.logerr(f"❌ Enhanced GPS Localization Node error: {e}") 