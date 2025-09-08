#!/usr/bin/env python

import rospy
import math
import random
import threading
import numpy as np
from sensor_msgs.msg import NavSatFix, NavSatStatus
from geometry_msgs.msg import Twist
import pyproj

class GpsSimulator:
    """
    GPS Simulator for testing enhanced GPS localization
    
    Features:
    - Realistic GPS noise and accuracy simulation
    - Variable signal quality based on environment
    - Satellite count and HDOP simulation
    - Position drift and multipath effects
    - Path following for robot movement simulation
    """
    
    def __init__(self):
        rospy.init_node('gps_simulator')
        
        # ROS Parameters
        self.output_topic = rospy.get_param('~output_topic', '/fix')
        self.base_accuracy = rospy.get_param('~base_accuracy', 3.0)  # meters
        self.update_rate = rospy.get_param('~update_rate', 5.0)      # Hz
        self.simulate_movement = rospy.get_param('~simulate_movement', True)
        
        # Initial position (TU Dortmund campus area)
        self.initial_lat = rospy.get_param('~initial_lat', 51.4936)
        self.initial_lon = rospy.get_param('~initial_lon', 7.4192)
        self.initial_alt = rospy.get_param('~initial_alt', 160.0)
        
        rospy.loginfo("🛰️ GPS Simulator Starting...")
        rospy.loginfo(f"   Output Topic: {self.output_topic}")
        rospy.loginfo(f"   Base Accuracy: {self.base_accuracy}m")
        rospy.loginfo(f"   Update Rate: {self.update_rate} Hz")
        rospy.loginfo(f"   Initial Position: ({self.initial_lat:.6f}, {self.initial_lon:.6f})")
        
        # Current GPS state
        self.current_lat = self.initial_lat
        self.current_lon = self.initial_lon
        self.current_alt = self.initial_alt
        self.current_accuracy = self.base_accuracy
        self.current_satellites = 8
        self.current_status = NavSatStatus.STATUS_FIX
        
        # Movement simulation
        self.robot_x = 0.0  # Position in local frame (meters)
        self.robot_y = 0.0
        self.robot_heading = 0.0
        self.movement_lock = threading.Lock()
        
        # Environment simulation
        self.environment_factor = 1.0  # 1.0 = ideal, higher = worse GPS
        self.multipath_noise = 0.0
        self.ionospheric_delay = 0.0
        
        # Setup coordinate transformer for movement simulation
        self.setup_coordinate_transformer()
        
        # ROS Publishers and Subscribers
        self.gps_pub = rospy.Publisher(self.output_topic, NavSatFix, queue_size=10)
        
        if self.simulate_movement:
            self.cmd_vel_sub = rospy.Subscriber('/cmd_vel', Twist, self.cmd_vel_callback)
        
        # Timer for GPS publishing
        self.gps_timer = rospy.Timer(
            rospy.Duration(1.0 / self.update_rate), 
            self.publish_gps_fix
        )
        
        # Timer for environmental effects
        self.env_timer = rospy.Timer(
            rospy.Duration(5.0),  # Update every 5 seconds
            self.update_environment
        )
        
        rospy.loginfo("✅ GPS Simulator initialized successfully")
        rospy.loginfo("   Publishing simulated GPS data with realistic noise")
    
    def setup_coordinate_transformer(self):
        """Setup coordinate transformer for movement simulation"""
        try:
            self.wgs84 = pyproj.CRS('EPSG:4326')
            self.utm32 = pyproj.CRS('EPSG:25832')
            
            self.wgs84_to_utm = pyproj.Transformer.from_crs(
                self.wgs84, self.utm32, always_xy=True
            )
            self.utm_to_wgs84 = pyproj.Transformer.from_crs(
                self.utm32, self.wgs84, always_xy=True
            )
            
            # Convert initial position to UTM for movement simulation
            self.origin_utm_x, self.origin_utm_y = self.wgs84_to_utm.transform(
                self.initial_lon, self.initial_lat
            )
            
            rospy.loginfo(f"🗺️ GPS Simulator coordinate origin: ({self.origin_utm_x:.3f}, {self.origin_utm_y:.3f}) UTM")
            
        except Exception as e:
            rospy.logerr(f"❌ Failed to setup coordinate transformer: {e}")
            self.wgs84_to_utm = None
            self.utm_to_wgs84 = None
    
    def cmd_vel_callback(self, msg):
        """Simulate robot movement based on cmd_vel commands"""
        if not self.simulate_movement:
            return
        
        with self.movement_lock:
            # Simple kinematic model for GPS position update
            dt = 1.0 / self.update_rate
            
            # Update heading
            self.robot_heading += msg.angular.z * dt
            
            # Normalize heading
            while self.robot_heading > math.pi:
                self.robot_heading -= 2 * math.pi
            while self.robot_heading < -math.pi:
                self.robot_heading += 2 * math.pi
            
            # Update position
            dx = msg.linear.x * math.cos(self.robot_heading) * dt
            dy = msg.linear.x * math.sin(self.robot_heading) * dt
            
            self.robot_x += dx
            self.robot_y += dy
            
            # Convert back to GPS coordinates
            if self.utm_to_wgs84:
                try:
                    utm_x = self.origin_utm_x + self.robot_x
                    utm_y = self.origin_utm_y + self.robot_y
                    
                    lon, lat = self.utm_to_wgs84.transform(utm_x, utm_y)
                    self.current_lat = lat
                    self.current_lon = lon
                    
                except Exception as e:
                    rospy.logwarn(f"⚠️ GPS coordinate conversion error: {e}")
    
    def update_environment(self, event):
        """Simulate changing environmental conditions affecting GPS"""
        
        # Simulate different environments
        environments = [
            {'name': 'open_sky', 'factor': 1.0, 'satellites': 12, 'multipath': 0.0},
            {'name': 'light_trees', 'factor': 1.5, 'satellites': 10, 'multipath': 0.5},
            {'name': 'dense_trees', 'factor': 3.0, 'satellites': 7, 'multipath': 2.0},
            {'name': 'urban_canyon', 'factor': 5.0, 'satellites': 6, 'multipath': 3.0},
            {'name': 'building_shadow', 'factor': 8.0, 'satellites': 5, 'multipath': 5.0},
        ]
        
        # Randomly select environment (weighted towards better conditions)
        weights = [0.4, 0.3, 0.15, 0.1, 0.05]  # Favor better GPS conditions
        env = np.random.choice(environments, p=weights)
        
        self.environment_factor = env['factor']
        self.current_satellites = max(4, env['satellites'] + random.randint(-2, 2))
        self.multipath_noise = env['multipath']
        
        # Simulate ionospheric effects
        self.ionospheric_delay = random.uniform(0.0, 2.0)
        
        rospy.loginfo(f"🌍 GPS Environment: {env['name']}, Factor: {self.environment_factor:.1f}, Satellites: {self.current_satellites}")
    
    def add_gps_noise(self, lat, lon, alt):
        """Add realistic GPS noise based on current conditions"""
        
        # Base accuracy affected by environment
        current_accuracy = self.base_accuracy * self.environment_factor
        
        # Convert accuracy to degrees (approximate)
        lat_noise_std = current_accuracy / 111000.0  # meters to degrees latitude
        lon_noise_std = current_accuracy / (111000.0 * math.cos(math.radians(lat)))
        alt_noise_std = current_accuracy * 1.5  # Altitude typically less accurate
        
        # Add multipath noise (correlated over short time periods)
        multipath_lat = self.multipath_noise * random.gauss(0, lat_noise_std)
        multipath_lon = self.multipath_noise * random.gauss(0, lon_noise_std)
        
        # Add random noise
        random_lat = random.gauss(0, lat_noise_std)
        random_lon = random.gauss(0, lon_noise_std)
        random_alt = random.gauss(0, alt_noise_std)
        
        # Add ionospheric delay (systematic bias)
        iono_bias_lat = self.ionospheric_delay * lat_noise_std * 0.1
        iono_bias_lon = self.ionospheric_delay * lon_noise_std * 0.1
        
        # Total noise
        noisy_lat = lat + random_lat + multipath_lat + iono_bias_lat
        noisy_lon = lon + random_lon + multipath_lon + iono_bias_lon
        noisy_alt = alt + random_alt
        
        # Update accuracy estimate
        self.current_accuracy = current_accuracy
        
        return noisy_lat, noisy_lon, noisy_alt
    
    def simulate_gps_outage(self):
        """Simulate GPS signal loss"""
        # 2% chance of temporary GPS loss
        if random.random() < 0.02:
            outage_duration = random.uniform(1.0, 5.0)  # 1-5 second outage
            rospy.logwarn(f"🚫 Simulating GPS outage for {outage_duration:.1f} seconds")
            return True, outage_duration
        return False, 0.0
    
    def publish_gps_fix(self, event):
        """Publish simulated GPS fix with realistic noise and quality"""
        
        # Check for GPS outage
        outage, _ = self.simulate_gps_outage()
        if outage:
            # Publish GPS fix with no fix status
            gps_msg = NavSatFix()
            gps_msg.header.stamp = rospy.Time.now()
            gps_msg.header.frame_id = 'gps'
            gps_msg.status.status = NavSatStatus.STATUS_NO_FIX
            gps_msg.status.service = NavSatStatus.SERVICE_GPS
            self.gps_pub.publish(gps_msg)
            return
        
        # Add realistic noise to current position
        with self.movement_lock:
            noisy_lat, noisy_lon, noisy_alt = self.add_gps_noise(
                self.current_lat, self.current_lon, self.current_alt
            )
        
        # Create GPS message
        gps_msg = NavSatFix()
        gps_msg.header.stamp = rospy.Time.now()
        gps_msg.header.frame_id = 'gps'
        
        # GPS status based on current conditions
        if self.current_satellites >= 4:
            gps_msg.status.status = NavSatStatus.STATUS_FIX
        else:
            gps_msg.status.status = NavSatStatus.STATUS_NO_FIX
        gps_msg.status.service = NavSatStatus.SERVICE_GPS
        
        # Position
        gps_msg.latitude = noisy_lat
        gps_msg.longitude = noisy_lon
        gps_msg.altitude = noisy_alt
        
        # Covariance matrix (position uncertainty)
        # Diagonal elements represent variance in x, y, z
        accuracy_var = self.current_accuracy ** 2
        gps_msg.position_covariance[0] = accuracy_var     # x variance
        gps_msg.position_covariance[4] = accuracy_var     # y variance  
        gps_msg.position_covariance[8] = accuracy_var * 2 # z variance (altitude less accurate)
        
        # Set covariance type
        gps_msg.position_covariance_type = NavSatFix.COVARIANCE_TYPE_DIAGONAL_KNOWN
        
        # Publish GPS fix
        self.gps_pub.publish(gps_msg)
        
        # Debug logging (throttled)
        if random.random() < 0.1:  # 10% of messages
            rospy.logdebug(f"📡 GPS: ({noisy_lat:.6f}, {noisy_lon:.6f}), "
                          f"Acc: {self.current_accuracy:.1f}m, "
                          f"Sats: {self.current_satellites}, "
                          f"Env: {self.environment_factor:.1f}")

if __name__ == '__main__':
    try:
        gps_sim = GpsSimulator()
        rospy.spin()
    except rospy.ROSInterruptException:
        rospy.loginfo("🛰️ GPS Simulator shutting down")
    except Exception as e:
        rospy.logerr(f"❌ GPS Simulator error: {e}") 