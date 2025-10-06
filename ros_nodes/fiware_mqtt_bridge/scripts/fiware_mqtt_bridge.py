#!/usr/bin/env python3

import rospy
import json
import ssl
import threading
import time
import yaml
import os
import requests
import urllib.request
import shutil
from datetime import datetime
from enum import Enum
import pyproj

import paho.mqtt.client as mqtt
from std_msgs.msg import String
from geometry_msgs.msg import Twist, PoseStamped
from nav_msgs.msg import Odometry
from actionlib import SimpleActionClient
from move_base_msgs.msg import MoveBaseAction, MoveBaseGoal

class RobotState(Enum):
    """Robot states as defined in FIWARE integration plan"""
    ON_SERVICE = "On Service"
    IDLE = "Idle"
    MISSION_RECEIVED = "Mission Received"
    MAP_DOWNLOAD = "Map Download"
    PLANNING = "Planning"
    MISSION_EXECUTION = "Mission Execution"
    MISSION_COMPLETED = "Mission Completed"
    ERROR = "Error"
    CHARGING = "Charging"

class FiwareMqttBridge:
    """
    FIWARE MQTT Bridge for Robot Communication
    
    Implements:
    - MQTT subscription to FIWARE CommandMessage topics
    - State publishing to FIWARE StateMessage topics
    - ROS integration with navigation stack
    - Robot state management
    - Dynamic map management
    """
    
    def __init__(self):
        rospy.init_node('fiware_mqtt_bridge', anonymous=True)
        
        # Load configuration
        self.load_config()
        
        # Initialize state
        self.current_state = RobotState.ON_SERVICE
        self.previous_state = RobotState.ON_SERVICE
        self.current_position = self.config['state']['simulation']['initial_position'].copy()
        self.current_map_id = None
        self.current_mission = None
        self.battery_level = 85.0  # Simulated battery
        
        # Error tracking
        self.last_error = None
        self.last_transition_reason = ""
        
        # Error tracking
        self.last_error = None
        self.last_transition_reason = ""
        
        # Map management
        self.backend_url = self.config.get('maps', {}).get('backend_url', 'http://localhost:8000/api/maps')
        self.local_maps_path = self.config.get('maps', {}).get('local_path', '/tmp/fiware_maps')
        
        # Ensure local maps directory exists
        os.makedirs(self.local_maps_path, exist_ok=True)
        
        # MQTT client
        self.mqtt_client = None
        self.mqtt_connected = False
        
        # MQTT connectivity monitoring
        self.has_mqtt_connectivity = False
        self.connection_monitor_thread = None
        self.connection_monitor_running = False
        self.last_connectivity_check = 0
        
        # Load connection monitoring configuration
        connection_config = self.config.get('connection_monitoring', {})
        self.connectivity_check_interval = connection_config.get('check_interval', 0.5)  # Very aggressive: check every 0.5 seconds
        self.mqtt_timeout = connection_config.get('mqtt_timeout', 1.0)  # Very fast timeout
        self.cache_successful_checks = connection_config.get('cache_successful_checks', False)  # Disable caching
        self.cache_duration = connection_config.get('cache_duration', 0.1)  # Minimal cache duration
        
        # ROS publishers and subscribers
        self.setup_ros_interface()
        
        # Navigation client
        self.move_base_client = None
        self.setup_navigation()
        
        # State publishing timer
        self.state_timer = None
        
        # Coordinate transformer
        self.transformer = None
        self.setup_coordinate_transformer()
        
        rospy.loginfo("FIWARE MQTT Bridge initialized")
        rospy.loginfo(f"Map backend URL: {self.backend_url}")
        rospy.loginfo(f"Local maps path: {self.local_maps_path}")
    
    def load_config(self):
        """Load configuration from YAML file"""
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 
            'config', 
            'fiware_config.yaml'
        )
        
        try:
            with open(config_path, 'r') as f:
                self.config = yaml.safe_load(f)
            rospy.loginfo(f"Configuration loaded from {config_path}")
        except Exception as e:
            rospy.logerr(f"Failed to load configuration: {e}")
            # Use default configuration
            self.config = self.get_default_config()
    
    def get_default_config(self):
        """Return default configuration if file loading fails"""
        return {
            'mqtt': {
                'host': 'mosquitto.ikt.fh-dortmund.de',
                'port': 8883,
                'username': 'iot-client',
                'password': 'crYsARBqeT2R',
                'use_tls': True,
                'insecure': True,
                'keepalive': 5,  # 5 seconds keepalive for fast disconnection detection
            },
            'robot': {
                'id': 'Professor_Robot_01'
            },
            'topics': {
                'command': {
                    'pattern': '/8jggokgpepnvsb2uv4s40d59vk/Professor_Robot_01/cmd'
                },
                'state': {
                    'pattern': '/json/8jggokgpepnvsb2uv4s40d59vk/Professor_Robot_01/attrs'
                },
                'command_ack': {
                    'pattern': '/json/8jggokgpepnvsb2uv4s40d59vk/Professor_Robot_01/attrs'
                }
            },
            'state': {
                'publish_rate': 1.0,
                'simulation': {
                    'enabled': False,
                    'initial_position': [80.0, 17.0, 0.0]
                }
            },
            'navigation': {
                'move_base_action': '/move_base',
                'goal_tolerance': 0.5,
                'goal_timeout': 300
            },
            'maps': {
                'backend_url': 'http://10.215.140.245:8000/api/maps',
                'local_path': '/tmp/fiware_maps'
            },
            'backend': {
                'url': 'http://10.215.140.245:8000'
            },
            'connection_monitoring': {
                'check_interval': 0.5,  # Ultra-aggressive: check every 0.5 seconds
                'mqtt_connectivity_check': True,
                'mqtt_keepalive_check': True,
                'mqtt_timeout': 1.0,  # Very fast timeout
                'cache_successful_checks': False,  # Disable caching
                'cache_duration': 0.1  # Minimal cache duration
            }
        }
    
    def setup_ros_interface(self):
        """Setup ROS publishers and subscribers"""
        # Subscribers
        self.odom_sub = rospy.Subscriber('/odom', Odometry, self.odom_callback)
        self.cmd_vel_sub = rospy.Subscriber('/cmd_vel', Twist, self.cmd_vel_callback)
        
        # Map switch integration
        self.map_switch_status_sub = rospy.Subscriber('/robot/map_switch_status', String, self.map_switch_status_callback)
        
        # Publishers
        self.status_pub = rospy.Publisher('/fiware/robot_status', String, queue_size=10)
        self.map_switch_request_pub = rospy.Publisher('/robot/switch_map_request', String, queue_size=10)
        
        rospy.loginfo("ROS interface setup complete")
        rospy.loginfo("Map switch integration: listening to /robot/map_switch_status, publishing to /robot/switch_map_request")
    
    def setup_navigation(self):
        """Setup navigation action client"""
        try:
            move_base_action = self.config['navigation']['move_base_action']
            self.move_base_client = SimpleActionClient(move_base_action, MoveBaseAction)
            rospy.loginfo(f"Waiting for move_base action server at {move_base_action}...")
            
            # Wait for action server with timeout
            if self.move_base_client.wait_for_server(rospy.Duration(10.0)):
                rospy.loginfo("Move base action server connected")
            else:
                rospy.logwarn("Move base action server not available - navigation disabled")
                self.move_base_client = None
        except Exception as e:
            rospy.logerr(f"Failed to setup navigation: {e}")
            self.move_base_client = None
    
    def setup_mqtt(self):
        """Setup MQTT client and connect to broker"""
        try:
            self.mqtt_client = mqtt.Client()
            
            # Set callbacks
            self.mqtt_client.on_connect = self.on_mqtt_connect
            self.mqtt_client.on_disconnect = self.on_mqtt_disconnect
            self.mqtt_client.on_message = self.on_mqtt_message
            
            # Set authentication
            mqtt_config = self.config['mqtt']
            self.mqtt_client.username_pw_set(
                mqtt_config['username'], 
                mqtt_config['password']
            )
            
            # Configure keepalive for fast disconnection detection
            keepalive_interval = mqtt_config.get('keepalive', 5)
            self.mqtt_client.keepalive = keepalive_interval
            rospy.loginfo(f"MQTT keepalive set to {keepalive_interval} seconds")
            
            # Setup TLS
            if mqtt_config.get('use_tls', True):
                context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
                if mqtt_config.get('insecure', False):
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                self.mqtt_client.tls_set_context(context)
            
            # Connect to broker with short keepalive
            rospy.loginfo(f"Connecting to MQTT broker {mqtt_config['host']}:{mqtt_config['port']} with {keepalive_interval}s keepalive")
            self.mqtt_client.connect(
                mqtt_config['host'], 
                mqtt_config['port'], 
                keepalive_interval
            )
            
            # Start MQTT loop in separate thread
            self.mqtt_client.loop_start()
            
            return True
            
        except Exception as e:
            rospy.logerr(f"Failed to setup MQTT: {e}")
            return False
            

    
    def on_mqtt_connect(self, client, userdata, flags, rc):
        """MQTT connection callback"""
        if rc == 0:
            rospy.loginfo("Connected to MQTT broker successfully")
            self.mqtt_connected = True
            
            # Subscribe to command topic
            command_topic = self.config['topics']['command']['pattern']
            client.subscribe(command_topic)
            rospy.loginfo(f"Subscribed to command topic: {command_topic}")
            
            # Trigger connectivity check
            self.check_mqtt_connectivity_and_update_state()
            
        else:
            rospy.logerr(f"Failed to connect to MQTT broker. Return code: {rc}")
            self.mqtt_connected = False
            # Trigger connectivity check
            self.check_mqtt_connectivity_and_update_state()
    
    def on_mqtt_disconnect(self, client, userdata, rc):
        """MQTT disconnection callback"""
        rospy.logwarn(f"Disconnected from MQTT broker. Return code: {rc}")
        self.mqtt_connected = False
        # Trigger immediate connectivity check
        self.check_mqtt_connectivity_and_update_state()
    
    def on_mqtt_message(self, client, userdata, msg):
        """MQTT message received callback"""
        try:
            topic = msg.topic
            payload = msg.payload.decode('utf-8')
            
            rospy.loginfo(f"Received MQTT message on topic: {topic}")
            rospy.logdebug(f"Message payload: {payload}")
            
            # Parse JSON payload
            message_data = json.loads(payload)
            
            # Check if this is a command message
            if self.is_command_topic(topic):
                self.handle_command_message(message_data)
            else:
                rospy.logwarn(f"Unknown message topic: {topic}")
                
        except json.JSONDecodeError as e:
            rospy.logerr(f"Failed to parse JSON message: {e}")
        except Exception as e:
            rospy.logerr(f"Error processing MQTT message: {e}")
    
    def is_command_topic(self, topic):
        """Check if topic is a command topic"""
        command_pattern = self.config['topics']['command']['pattern']
        return topic == command_pattern
    
    def check_mqtt_connectivity(self):
        """Check MQTT connectivity using simple connection flag"""
        if not self.mqtt_client:
            return False
        
        # Simple check: just use the connection flag set by MQTT callbacks
        # The callbacks are working fine - we saw immediate disconnect detection
        return self.mqtt_connected
    
    def check_mqtt_connectivity_and_update_state(self):
        """MQTT connectivity check - single source of truth for robot operation"""
        try:
            if self.check_mqtt_connectivity():
                if not self.has_mqtt_connectivity:
                    rospy.loginfo("✅ MQTT connectivity restored")
                    self.has_mqtt_connectivity = True
                    if self.current_state == RobotState.ERROR:
                        self.transition_state(RobotState.IDLE, "MQTT connectivity restored")
                return True
            else:
                if self.has_mqtt_connectivity:
                    rospy.logwarn("❌ MQTT connectivity lost")
                    self.has_mqtt_connectivity = False
                    self.transition_state(RobotState.ERROR, "MQTT connectivity lost - robot stopping")
                return False
        except Exception as e:
            rospy.logerr(f"MQTT connectivity check error: {e}")
            if self.has_mqtt_connectivity:
                self.has_mqtt_connectivity = False
                self.transition_state(RobotState.ERROR, "MQTT connectivity check failed")
            return False
    
    def is_robot_busy(self):
        """
        Check if robot is currently executing a mission and should reject new missions.
        
        Returns:
            bool: True if robot is busy executing a mission, False if available
        """
        # Check if robot is in busy states
        busy_states = [
            RobotState.MISSION_EXECUTION,
            RobotState.PLANNING,
            RobotState.MAP_DOWNLOAD
        ]
        
        # Robot is busy if in a busy state AND has an active mission
        is_in_busy_state = self.current_state in busy_states
        has_active_mission = self.current_mission is not None
        
        rospy.logdebug(f"Robot busy check: state={self.current_state.value}, has_mission={has_active_mission}")
        
        return is_in_busy_state and has_active_mission
    
    def handle_command_message(self, message_data):
        """Handle received CommandMessage"""
        try:
            rospy.loginfo("Processing CommandMessage")
            rospy.loginfo(f"Raw message data: {message_data}")
            
            # Handle both legacy and IoT Agent command formats
            if 'command' in message_data:
                if isinstance(message_data['command'], dict):
                    # Old format: {"command": {"command": "MOVE_TO", ...}}
                    command_info = message_data['command']
                    rospy.loginfo("Using legacy command format")
                elif isinstance(message_data['command'], str):
                    # IoT Agent format: command is a JSON string
                    try:
                        command_info = json.loads(message_data['command'])
                        rospy.loginfo("Parsed IoT Agent command string as JSON")
                    except Exception as e:
                        rospy.logerr(f"Failed to parse command string as JSON: {e}")
                        return
                else:
                    rospy.logerr(f"Unknown command field type: {type(message_data['command'])}")
                    return
            else:
                # New format: direct JSON object
                command_info = message_data
                rospy.loginfo("Using direct command format")
            
            # Extract command information from parsed data
            command_type = command_info.get('command', '')
            command_time = command_info.get('commandTime', '')
            waypoints = command_info.get('waypoints', {})
            map_id = command_info.get('mapId', '')
            
            rospy.loginfo(f"Parsed Command: {command_type}, MapID: {map_id}")
            rospy.loginfo(f"Command Info: {command_info}")
            
            # Import required modules for datetime operations
            from datetime import datetime
            import pytz
            import uuid
            
            # Extract mission ID for potential rejection
            mission_id = command_info.get('missionId')
            if not mission_id:
                # Generate a temporary mission ID if not provided
                mission_id = f"temp_mission_{uuid.uuid4().hex[:8]}"
                rospy.logwarn(f"No missionId in command, using temporary ID: {mission_id}")
            
            # Check if robot is busy (except for STOP commands which should always be processed)
            if command_type != "STOP" and self.is_robot_busy():
                rospy.logwarn(f"🚫 Rejecting incoming {command_type} mission - robot is currently executing another mission")
                rospy.loginfo(f"Current mission: {self.current_mission['missionId']} in state: {self.current_state.value}")
                
                # Send rejection acknowledgment
                self.send_command_acknowledgment(command_info, "REJECTED")
                
                # Update incoming mission status to failed in backend
                rejection_reason = f"Robot is currently executing mission {self.current_mission['missionId']}"
                failed_time = datetime.now(pytz.timezone("Europe/Berlin")).isoformat()
                self.update_mission_status_backend(
                    mission_id, 
                    "failed", 
                    completed_time=failed_time,
                    error_message=rejection_reason
                )
                
                rospy.loginfo(f"✅ Mission {mission_id} rejected and marked as failed in backend")
                return  # Exit early without processing the command
            
            # Update state only if we're accepting the command
            self.transition_state(RobotState.MISSION_RECEIVED, 
                                f"Received {command_type} command")
            
            # Send acknowledgment
            self.send_command_acknowledgment(command_info, "ACCEPTED")
            
            # Process the command
            if command_type == "MOVE_TO":
                # Store current mission - only if we're accepting it
                self.current_mission = {
                    'missionId': mission_id,
                    'command': command_type,
                    'commandTime': command_time,
                    'waypoints': waypoints,
                    'mapId': map_id,
                    'receivedTime': datetime.utcnow().isoformat()
                }
                self.handle_move_to_command(waypoints, map_id)
            elif command_type == "STOP":
                # For STOP commands, don't create a new mission - work with existing one
                rospy.loginfo(f"Processing STOP command - keeping existing mission: {self.current_mission.get('missionId') if self.current_mission else 'None'}")
                self.handle_stop_command()
            else:
                rospy.logwarn(f"Unknown command type: {command_type}")
                self.send_command_acknowledgment(command_info, "REJECTED")
                
        except Exception as e:
            rospy.logerr(f"Error handling command message: {e}")
            self.transition_state(RobotState.ERROR, f"Command processing error: {e}")
    
    def check_map_exists(self, map_id):
        """Check if map exists locally"""
        if not map_id:
            return False
        
        map_dir = os.path.join(self.local_maps_path, map_id)
        yaml_path = os.path.join(map_dir, 'map.yaml')
        
        if os.path.exists(yaml_path):
            # Check if image file also exists
            if os.path.exists(map_dir):
                image_files = [f for f in os.listdir(map_dir) if f.startswith('map.') and f.endswith(('.png', '.pgm'))]
                if image_files:
                    rospy.loginfo(f"Map {map_id} found locally at {map_dir}")
                    return True
        
        rospy.loginfo(f"Map {map_id} not found locally")
        return False
    
    def download_map_from_backend(self, map_id):
        """Download map from backend API"""
        try:
            rospy.loginfo(f"Downloading map {map_id} from backend...")
            
            # Get map files info from backend
            files_url = f"{self.backend_url}/{map_id}/files"
            rospy.loginfo(f"Requesting map files from: {files_url}")
            
            response = requests.get(files_url, timeout=10)
            response.raise_for_status()
            
            map_info = response.json()
            
            # Create local map directory
            map_dir = os.path.join(self.local_maps_path, map_id)
            os.makedirs(map_dir, exist_ok=True)
            
            # Save YAML file
            yaml_content = map_info['files']['yaml']['content']
            yaml_path = os.path.join(map_dir, 'map.yaml')
            with open(yaml_path, 'w') as f:
                f.write(yaml_content)
            
            rospy.loginfo(f"YAML file saved to: {yaml_path}")
            
            # Download image file
            image_filename = map_info['files']['image']['filename']
            image_url = f"{self.backend_url}/{map_id}/image"
            image_path = os.path.join(map_dir, image_filename)
            
            rospy.loginfo(f"Downloading image from: {image_url}")
            urllib.request.urlretrieve(image_url, image_path)
            
            rospy.loginfo(f"Image file saved to: {image_path}")
            
            # Update YAML file to use local image path and preserve original origin
            with open(yaml_path, 'r') as f:
                yaml_data = yaml.safe_load(f)
            
            yaml_data['image'] = image_filename
            
            # Preserve original map origin coordinates for real coordinate system support
            original_origin = yaml_data.get('origin', [0.0, 0.0, 0.0])
            rospy.loginfo(f"Preserving original map origin: {original_origin}")
            rospy.loginfo("Real coordinate system support: origin coordinates maintained")
            
            with open(yaml_path, 'w') as f:
                yaml.dump(yaml_data, f)
            
            rospy.loginfo(f"Map {map_id} downloaded successfully to {map_dir}")
            return True
            
        except requests.RequestException as e:
            rospy.logerr(f"Failed to download map {map_id}: HTTP error - {e}")
            return False
        except Exception as e:
            rospy.logerr(f"Failed to download map {map_id}: {e}")
            return False

    def map_switch_status_callback(self, msg):
        """Handle map switch status messages"""
        try:
            status = msg.data
            rospy.loginfo(f"Map switch status received: {status}")
            
            if status.startswith("SUCCESS:"):
                # Map switch successful
                rospy.loginfo("Map switch completed successfully - localization should now be stable")
                # Continue with navigation planning
                # The planning state transition will happen in handle_move_to_command
            elif status.startswith("ERROR:"):
                # Map switch failed
                rospy.logerr(f"Map switch failed: {status}")
                self.transition_state(RobotState.ERROR, f"Map switch failed: {status}")
            
        except Exception as e:
            rospy.logerr(f"Error processing map switch status: {e}")
    
    def request_map_switch(self, map_id):
        """Request map switch via ROS topic"""
        try:
            if not map_id:
                rospy.logwarn("No map_id provided for map switch")
                return False
            
            rospy.loginfo(f"Requesting map switch to: {map_id}")
            
            # Publish map switch request
            msg = String()
            msg.data = map_id
            self.map_switch_request_pub.publish(msg)
            
            # Wait a moment for the request to be processed
            rospy.sleep(0.5)
            
            return True
            
        except Exception as e:
            rospy.logerr(f"Error requesting map switch: {e}")
            return False

    def handle_move_to_command(self, waypoints, map_id):
        """Handle MOVE_TO command with map management"""
        try:
            # Extract coordinates (WGS84 lon, lat)
            coordinates = waypoints.get('coordinates', [])
            if len(coordinates) < 2:
                raise ValueError("Invalid waypoints coordinates")
            
            # Coordinates order in GeoJSON is [lon, lat]
            lon, lat = coordinates[0], coordinates[1]
            
            try:
                target_x, target_y = self.wgs84_to_utm_xy(lon, lat)
            except Exception as tr_err:
                rospy.logerr(f"Coordinate transformation error: {tr_err}")
                self.transition_state(RobotState.ERROR, "Coordinate transformation failed")
                return
            
            target_z = coordinates[2] if len(coordinates) > 2 else 0.0
            
            rospy.loginfo(f"MOVE_TO target: x={target_x}, y={target_y}, z={target_z}")
            rospy.loginfo(f"Robot current position: x={self.current_position[0]:.3f}, y={self.current_position[1]:.3f}")
            
            # Check if map change is needed
            if map_id and map_id != self.current_map_id:
                rospy.loginfo(f"Map change required: {self.current_map_id} -> {map_id}")
                
                # Check if map exists locally
                if not self.check_map_exists(map_id):
                    # Transition to map download state
                    self.transition_state(RobotState.MAP_DOWNLOAD, f"Downloading map {map_id}")
                    
                    # Download map from backend
                    if not self.download_map_from_backend(map_id):
                        self.transition_state(RobotState.ERROR, f"Failed to download map {map_id}")
                        return
                    
                    rospy.loginfo(f"Map {map_id} downloaded successfully")
                
                # Request map switch via ROS service
                rospy.loginfo(f"Requesting map server restart with map {map_id}")
                if not self.request_map_switch(map_id):
                    self.transition_state(RobotState.ERROR, f"Failed to request map switch to {map_id}")
                    return
                
                # Update current map ID
                self.current_map_id = map_id
                rospy.loginfo(f"Map switch initiated for {map_id}")
                
                # Wait for map switch to complete before sending goal
                rospy.loginfo("Waiting for map switch to complete...")
                rospy.sleep(2.0)  # Give map_server time to restart and localization to stabilize
                rospy.loginfo(f"Current robot position after map switch: ({self.current_position[0]:.3f}, {self.current_position[1]:.3f})")
            
            # Transition to planning state
            self.transition_state(RobotState.PLANNING, "Generating navigation path")
            
            # Convert absolute UTM coordinates to map-relative coordinates (for logging/verification)
            # NOTE: Goals must be expressed in the 'map' frame using ABSOLUTE map coordinates.
            #       When the map YAML origin is non-zero (e.g., UTM), sending map-relative
            #       coordinates with frame_id='map' will place the goal off the global costmap.
            #       Therefore, we always send absolute coordinates in the map frame.
            map_relative_x, map_relative_y = self.convert_utm_to_map_coordinates(target_x, target_y, map_id)
            
            # Create navigation goal
            if self.move_base_client:
                goal = MoveBaseGoal()
                goal.target_pose.header.frame_id = "map"
                goal.target_pose.header.stamp = rospy.Time.now()
                # Use absolute coordinates in the 'map' frame
                # If the map origin is [0, 0, 0], these equal the map-relative values.
                goal.target_pose.pose.position.x = target_x
                goal.target_pose.pose.position.y = target_y
                goal.target_pose.pose.position.z = target_z
                goal.target_pose.pose.orientation.w = 1.0  # No rotation
                
                # Log goal details for debugging
                rospy.loginfo(f"Created navigation goal: frame_id={goal.target_pose.header.frame_id}")
                rospy.loginfo(f"Goal position (map frame, absolute): x={target_x}, y={target_y}, z={target_z}")
                rospy.loginfo(f"Also computed (map-relative for debug): x={map_relative_x}, y={map_relative_y}, z={target_z}")
                
                # Transition to execution state
                self.transition_state(RobotState.MISSION_EXECUTION, "Executing navigation")
                
                # Send goal with callbacks
                rospy.loginfo("Sending navigation goal to move_base")
                self.move_base_client.send_goal(
                    goal,
                    done_cb=self.navigation_done_callback,
                    active_cb=self.navigation_active_callback,
                    feedback_cb=self.navigation_feedback_callback
                )
                
                # Update mission status to in_progress when goal is sent
                if self.current_mission and 'missionId' in self.current_mission:
                    from datetime import datetime
                    import pytz
                    executed_time = datetime.now(pytz.timezone("Europe/Berlin")).isoformat()
                    self.update_mission_status_backend(self.current_mission['missionId'], "in_progress", executed_time=executed_time)
                
                # Set timeout for navigation
                self.navigation_start_time = rospy.Time.now()
                self.navigation_timeout = rospy.Duration(300)  # 5 minutes timeout
            else:
                rospy.logwarn("Move base client not available - simulating movement")
                self.simulate_movement(target_x, target_y, target_z)
                
        except Exception as e:
            rospy.logerr(f"Error handling MOVE_TO command: {e}")
            self.transition_state(RobotState.ERROR, f"Navigation error: {e}")
    
    def handle_stop_command(self):
        """Handle STOP command - cancel current navigation"""
        try:
            rospy.loginfo("🛑 Received STOP command")
            
            # Cancel any active navigation goals
            if self.move_base_client:
                self.move_base_client.cancel_all_goals()
                rospy.loginfo("Navigation goals cancelled")
            
            # Transition to idle state
            self.transition_state(RobotState.IDLE, "Mission stopped by user command")
            
        except Exception as e:
            rospy.logerr(f"Error handling STOP command: {e}")
            self.transition_state(RobotState.ERROR, f"Stop command error: {e}")
    

    
    def navigation_done_callback(self, status, result):
        """Callback when navigation goal is completed"""
        try:
            from actionlib_msgs.msg import GoalStatus
            import pytz
            
            rospy.loginfo(f"Navigation goal finished with status: {status}")
            
            # Check if robot is already in IDLE state (e.g., from STOP command)
            if self.current_state == RobotState.IDLE:
                rospy.loginfo("🤖 Robot already in IDLE state - skipping navigation callback state transition")
                return
            
            if status == GoalStatus.SUCCEEDED:
                rospy.loginfo("🎯 Navigation goal SUCCEEDED!")
                self.transition_state(RobotState.MISSION_COMPLETED, "Navigation goal achieved successfully")
                completed_time = datetime.now(pytz.timezone("Europe/Berlin")).isoformat()
                self.update_mission_status_backend(self.current_mission['missionId'], "completed", completed_time=completed_time)
                # Return to idle after brief delay
                rospy.Timer(rospy.Duration(3.0), self.return_to_idle, oneshot=True)
                
            elif status == GoalStatus.ABORTED:
                rospy.logwarn("⚠️ Navigation goal ABORTED - no path found")
                rospy.loginfo("🔄 Cancelling mission and returning to IDLE (no recovery rotation)")
                self.transition_state(RobotState.IDLE, "Navigation aborted - no path found, mission cancelled")
                self.update_mission_status_backend(self.current_mission['missionId'], "failed", completed_time=datetime.now(pytz.timezone("Europe/Berlin")).isoformat(), error_message="Navigation aborted - no path found")

            elif status == GoalStatus.REJECTED:
                rospy.logwarn("⚠️ Navigation goal REJECTED - invalid goal")
                rospy.loginfo("🔄 Cancelling mission and returning to IDLE")
                self.transition_state(RobotState.IDLE, "Navigation rejected - invalid goal, mission cancelled")
                self.update_mission_status_backend(self.current_mission['missionId'], "cancelled", completed_time=datetime.now(pytz.timezone("Europe/Berlin")).isoformat(), error_message="Navigation rejected - invalid goal")

            elif status == GoalStatus.PREEMPTED:
                rospy.logwarn("⚠️ Navigation goal PREEMPTED")
                rospy.loginfo("🔄 Navigation was preempted (likely by STOP command)")

                # Update mission status to cancelled if we have a current mission
                if self.current_mission and 'missionId' in self.current_mission:
                    completed_time = datetime.now(pytz.timezone("Europe/Berlin")).isoformat()
                    self.update_mission_status_backend(self.current_mission['missionId'], "cancelled", completed_time=completed_time, error_message="Mission cancelled by STOP command")
                    rospy.loginfo(f"Mission {self.current_mission['missionId']} marked as cancelled in backend")
                    
                    # Clear current mission after updating status
                    self.current_mission = None
                else:
                    rospy.logwarn("No current mission to cancel")
                
                # Ensure robot is in IDLE state (in case it wasn't already)
                if self.current_state != RobotState.IDLE:
                    self.transition_state(RobotState.IDLE, "Navigation preempted - returning to idle")

            else:
                rospy.logwarn(f"⚠️ Navigation goal finished with unknown status: {status}")
                rospy.loginfo("🔄 Returning to IDLE due to unknown navigation status")
                self.transition_state(RobotState.IDLE, f"Navigation completed with unknown status: {status}, returning to idle")
                self.update_mission_status_backend(self.current_mission['missionId'], "failed", completed_time=datetime.now(pytz.timezone("Europe/Berlin")).isoformat(), error_message=f"Navigation completed with unknown status: {status}")
        except Exception as e:
            rospy.logerr(f"Error in navigation done callback: {e}")
            self.transition_state(RobotState.ERROR, f"Navigation callback error: {e}")
    
    def navigation_active_callback(self):
        """Callback when navigation goal becomes active"""
        rospy.loginfo("🚀 Navigation goal is now ACTIVE - robot is moving")
    
    def navigation_feedback_callback(self, feedback):
        """Callback for navigation feedback - simple position tracking"""
        try:
            # Update current position from navigation feedback
            current_pose = feedback.base_position.pose
            x = current_pose.position.x
            y = current_pose.position.y
            
            rospy.logdebug(f"Navigation feedback - Robot position: ({x:.2f}, {y:.2f})")
            
            # Update current position
            self.current_position[0] = x
            self.current_position[1] = y
                    
        except Exception as e:
            rospy.logdebug(f"Error in navigation feedback callback: {e}")
    
    def return_to_idle(self, event):
        """Return robot to idle state after mission completion"""
        rospy.loginfo("🔄 Returning to IDLE state - ready for next mission")
        self.transition_state(RobotState.IDLE, "Mission completed, ready for next command")
        self.current_mission = None  # Clear current mission
    
    def simulate_movement(self, target_x, target_y, target_z):
        """Simulate robot movement for testing without navigation stack"""
        rospy.loginfo(f"Simulating movement to ({target_x}, {target_y}, {target_z})")
        
        # Update mission status to in_progress when simulation starts
        if self.current_mission and 'missionId' in self.current_mission:
            from datetime import datetime
            import pytz
            executed_time = datetime.now(pytz.timezone("Europe/Berlin")).isoformat()
            self.update_mission_status_backend(self.current_mission['missionId'], "in_progress", executed_time=executed_time)
        
        # Simple simulation - update position over time
        def simulation_thread():
            start_x, start_y = self.current_position[0], self.current_position[1]
            steps = 20
            
            for i in range(steps + 1):
                progress = float(i) / steps
                new_x = start_x + (target_x - start_x) * progress
                new_y = start_y + (target_y - start_y) * progress
                
                self.current_position[0] = new_x
                self.current_position[1] = new_y
                
                rospy.loginfo(f"Simulation step {i}/{steps}: ({new_x:.2f}, {new_y:.2f})")
                time.sleep(0.5)
            
            # Mission completed
            self.transition_state(RobotState.MISSION_COMPLETED, "Navigation simulation completed")
            
            # Update mission status to completed
            if self.current_mission and 'missionId' in self.current_mission:
                from datetime import datetime
                import pytz
                completed_time = datetime.now(pytz.timezone("Europe/Berlin")).isoformat()
                self.update_mission_status_backend(self.current_mission['missionId'], "completed", completed_time=completed_time)
            
            # Return to idle after delay
            rospy.sleep(2.0)
            self.transition_state(RobotState.IDLE, "Ready for next mission")
        
        # Start simulation in background thread
        thread = threading.Thread(target=simulation_thread)
        thread.daemon = True
        thread.start()
    
    def send_command_acknowledgment(self, original_command, status):
        """Send command acknowledgment via MQTT"""
        try:
            ack_topic = self.config['topics']['command_ack']['pattern']
            
            # Handle both dict and string command formats
            if isinstance(original_command, dict):
                command_val = original_command.get('command', '')
                command_time = original_command.get('commandTime', '')
                waypoints = original_command.get('waypoints', {})
                map_id = original_command.get('mapId', '')
            else:
                # If original_command is a string or other format, use defaults
                command_val = ''
                command_time = ''
                waypoints = {}
                map_id = ''
            
            ack_message = {
                "command": {"type": "command", "value": command_val},
                "commandTime": {"type": "Property", "value": command_time},
                "waypoints": {
                    "type": "GeoProperty",
                    "value": waypoints
                },
                "mapId": {"type": "Property", "value": map_id},
                "acknowledgmentStatus": status,
                "acknowledgmentTime": datetime.utcnow().isoformat() + "Z",
                "robotId": self.config['robot']['id']
            }
            
            payload = json.dumps(ack_message)
            
            if self.mqtt_client and self.mqtt_connected:
                self.mqtt_client.publish(ack_topic, payload)
                rospy.loginfo(f"Command acknowledgment sent: {status}")
            else:
                rospy.logwarn("Cannot send acknowledgment - MQTT not connected")
                
        except Exception as e:
            rospy.logerr(f"Error sending command acknowledgment: {e}")
    
    def publish_state_message(self):
        """Publish robot state via MQTT"""
        try:
            state_topic = self.config['topics']['state']['pattern']
            
            # Convert current_position (UTM) to WGS84 for FIWARE compliance
            try:
                lon, lat = self.utm_to_wgs84_lonlat(self.current_position[0], self.current_position[1])
                pose_geo = {
                    "type": "Point",
                    "coordinates": [lon, lat, self.current_position[2] if len(self.current_position) > 2 else 0.0]
                }
            except Exception as tr_err:
                rospy.logwarn(f"Coordinate conversion error in state publish: {tr_err}")
                pose_geo = {
                    "type": "Point",
                    "coordinates": [0.0, 0.0, 0.0]
                }
            
            # Destination conversion if available
            dest_geo = self.get_current_destination()
            if dest_geo.get("type") == "Point" and len(dest_geo.get("coordinates", [])) >= 2:
                dlon, dlat = dest_geo["coordinates"][:2]
                # If destination is still in UTM (legacy), convert
                if abs(dlon) > 180 or abs(dlat) > 90:
                    try:
                        dlon, dlat = self.utm_to_wgs84_lonlat(dlon, dlat)
                        dest_geo["coordinates"] = [dlon, dlat]
                    except Exception:
                        pass
            
            state_message = {
                "pose": pose_geo,
                "mode": "AUTONOMOUS",  # Fixed mode for autonomous robot
                "battery": self.battery_level,
                "accuracy": 0.9,  # GPS accuracy simulation
                "destination": dest_geo,
                "commandTime": self.get_current_command_time(),
                "errors": self.get_current_errors(),
                "robotState": self.current_state.value,
                "previousState": self.previous_state.value,
                "stateTransitionReason": getattr(self, 'last_transition_reason', ''),
                "currentMapId": self.current_map_id,
                "currentMissionId": self.current_mission.get('missionId') if self.current_mission else None,
                "isBusy": self.is_robot_busy(),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }
            
            payload = json.dumps(state_message)
            
            if self.mqtt_client and self.mqtt_connected:
                self.mqtt_client.publish(state_topic, payload)
                rospy.logdebug(f"State message published: {self.current_state.value}")
            else:
                rospy.logwarn("Cannot publish state - MQTT not connected")
                
        except Exception as e:
            rospy.logerr(f"Error publishing state message: {e}")
    
    def get_current_destination(self):
        """Get current mission destination"""
        if self.current_mission and 'waypoints' in self.current_mission:
            return self.current_mission['waypoints']
        return {"type": "Point", "coordinates": [0.0, 0.0, 0.0]}
    
    def get_current_command_time(self):
        """Get current mission command time"""
        if self.current_mission and 'commandTime' in self.current_mission:
            return self.current_mission['commandTime']
        return datetime.utcnow().isoformat() + "Z"
    
    def get_current_errors(self):
        """Get current error list with simple messages"""
        errors = []
        
        if self.current_state == RobotState.ERROR and self.last_error:
            error_detail = {
                "code": self.last_error,
                "message": self.last_error,
                "timestamp": datetime.now().isoformat(),
                "severity": "ERROR",
                "recovery_options": {
                    "manual_stop": "Send STOP command to cancel navigation and return to IDLE"
                }
            }
            
            errors.append(error_detail)
        
        return errors
    
    def transition_state(self, new_state, reason=""):
        """Transition to a new robot state with enhanced error recovery"""
        try:
            previous_state = self.current_state
            
            # Prevent redundant transitions to the same state
            if previous_state == new_state:
                rospy.logdebug(f"🤖 Already in {new_state.value} state - skipping redundant transition")
                return
            
            self.current_state = new_state
            self.last_transition_reason = reason
            
            rospy.loginfo(f"🔄 State transition: {previous_state.value} → {new_state.value}")
            if reason:
                rospy.loginfo(f"📝 Reason: {reason}")
            
            # ERROR state handling - connectivity issues and mission cancellation
            if new_state == RobotState.ERROR:
                self.last_error = reason
                rospy.logerr(f"❌ Entered ERROR state: {reason}")
                
                # Cancel any active navigation goals
                if self.move_base_client:
                    self.move_base_client.cancel_all_goals()
                    rospy.loginfo("Navigation goals cancelled due to ERROR state")
                
                # Update mission status if we have a current mission
                if self.current_mission and 'missionId' in self.current_mission:
                    from datetime import datetime
                    import pytz
                    completed_time = datetime.now(pytz.timezone("Europe/Berlin")).isoformat()
                    self.update_mission_status_backend(
                        self.current_mission['missionId'], 
                        "failed", 
                        completed_time=completed_time, 
                        error_message=f"Mission failed due to ERROR state: {reason}"
                    )
                
                # Clear current mission
                self.current_mission = None
                
                rospy.logwarn("🔧 Robot stopped - waiting for MQTT connectivity to restore")
            
            # Clear error when leaving ERROR state
            elif previous_state == RobotState.ERROR and new_state != RobotState.ERROR:
                self.last_error = None
                rospy.loginfo("✅ Recovered from ERROR state")
            
            # Publish state update
            self.publish_state_message()
            
                    # Special handling for different states
        # (removed start_navigation() call as it doesn't exist - navigation is started in handle_move_to_command)
                
        except Exception as e:
            rospy.logerr(f"Error in state transition: {e}")
    

    
    def odom_callback(self, msg):
        """Handle odometry updates from robot"""
        if not self.config['state']['simulation']['enabled']:
            # Use real odometry data
            self.current_position[0] = msg.pose.pose.position.x
            self.current_position[1] = msg.pose.pose.position.y
            # Extract yaw from quaternion if needed
    
    def cmd_vel_callback(self, msg):
        """Handle cmd_vel updates (for debugging)"""
        if msg.linear.x != 0 or msg.angular.z != 0:
            rospy.logdebug(f"Robot moving: linear={msg.linear.x}, angular={msg.angular.z}")
    
    def start_state_publishing(self):
        """Start periodic state publishing"""
        rate = self.config['state']['publish_rate']
        self.state_timer = rospy.Timer(rospy.Duration(1.0 / rate), self.state_publish_callback)
        rospy.loginfo(f"State publishing started at {rate} Hz")
    
    def state_publish_callback(self, event):
        """Timer callback for state publishing"""
        self.publish_state_message()
    
    def start_connection_monitoring(self):
        """Start MQTT connection monitoring thread"""
        if self.connection_monitor_running:
            rospy.logwarn("Connection monitoring already running")
            return
        
        self.connection_monitor_running = True
        self.connection_monitor_thread = threading.Thread(target=self.connection_monitor_loop)
        self.connection_monitor_thread.daemon = True
        self.connection_monitor_thread.start()
        rospy.loginfo("MQTT connection monitoring started")
    
    def stop_connection_monitoring(self):
        """Stop MQTT connection monitoring thread"""
        self.connection_monitor_running = False
        if self.connection_monitor_thread:
            self.connection_monitor_thread.join(timeout=2.0)
        rospy.loginfo("MQTT connection monitoring stopped")
    
    def connection_monitor_loop(self):
        """Background thread for monitoring MQTT connectivity"""
        rospy.loginfo("Connection monitor thread started")
        
        while self.connection_monitor_running and not rospy.is_shutdown():
            try:
                # Check MQTT connectivity every 0.5 seconds (very aggressive)
                self.check_mqtt_connectivity_and_update_state()
                rospy.sleep(self.connectivity_check_interval)
            except Exception as e:
                rospy.logerr(f"Error in connection monitor loop: {e}")
                rospy.sleep(0.1)  # Very short pause on error for fastest recovery
        
        rospy.loginfo("Connection monitor thread stopped")
    
    def run(self):
        """Main run loop with MQTT connectivity monitoring"""
        # Setup MQTT connection
        if not self.setup_mqtt():
            rospy.logwarn("Failed to setup MQTT - will continue without MQTT connection")
            # Don't exit, continue with ERROR state
            self.transition_state(RobotState.ERROR, "MQTT setup failed - robot stopping")
        else:
            # Wait for MQTT connection with timeout
            rospy.loginfo("Waiting for MQTT connection...")
            connection_timeout = 30.0  # 30 seconds timeout
            start_time = rospy.Time.now()
            
            while not self.mqtt_connected and not rospy.is_shutdown():
                if (rospy.Time.now() - start_time).to_sec() > connection_timeout:
                    rospy.logwarn("MQTT connection timeout - continuing without MQTT")
                    self.transition_state(RobotState.ERROR, "MQTT connection timeout - robot stopping")
                    break
                rospy.sleep(0.1)
            
            if self.mqtt_connected:
                # Transition to idle state only if MQTT is connected
                self.transition_state(RobotState.IDLE, "MQTT connected, ready for missions")
        
        # Start connection monitoring (regardless of initial MQTT status)
        self.start_connection_monitoring()
        
        # Start state publishing
        self.start_state_publishing()
        
        # Main loop
        rospy.loginfo("FIWARE MQTT Bridge running with connectivity monitoring")
        rospy.spin()
        
        # Cleanup
        self.stop_connection_monitoring()
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()

    def setup_coordinate_transformer(self):
        """Initialize PyProj coordinate transformers"""
        try:
            self.crs_wgs84 = pyproj.CRS('EPSG:4326')
            self.crs_utm32 = pyproj.CRS('EPSG:25832')
            self.wgs84_to_utm = pyproj.Transformer.from_crs(self.crs_wgs84, self.crs_utm32, always_xy=True)
            self.utm_to_wgs84 = pyproj.Transformer.from_crs(self.crs_utm32, self.crs_wgs84, always_xy=True)
            rospy.loginfo("Coordinate transformers ready (WGS84 ↔ UTM32N)")
        except Exception as e:
            rospy.logerr(f"Coordinate transformer init failed: {e}")
            self.wgs84_to_utm = None
            self.utm_to_wgs84 = None

    def wgs84_to_utm_xy(self, lon, lat):
        """Convert WGS84 lon/lat to UTM32 x/y"""
        if self.wgs84_to_utm is None:
            raise ValueError("Transformer not initialized")
        x, y = self.wgs84_to_utm.transform(lon, lat)
        return x, y

    def utm_to_wgs84_lonlat(self, x, y):
        """Convert UTM32 x/y to WGS84 lon/lat"""
        if self.utm_to_wgs84 is None:
            raise ValueError("Transformer not initialized")
        lon, lat = self.utm_to_wgs84.transform(x, y)
        return lon, lat
    
    def convert_utm_to_map_coordinates(self, utm_x, utm_y, map_id):
        """Convert absolute UTM coordinates to map-relative coordinates"""
        try:
            import yaml
            import os
            
            # Find the map file for the current/target map
            map_yaml_path = None
            
            if map_id:
                # Check downloaded maps first
                downloaded_path = os.path.join(self.local_maps_path, map_id, "map.yaml")
                if os.path.exists(downloaded_path):
                    map_yaml_path = downloaded_path
                else:
                    # Check default maps
                    default_path = "/mnt/c/ProjectThesisROS2Test/catkin_ws/src/professor_robot/maps/occupancy_grid.yaml"
                    if os.path.exists(default_path):
                        map_yaml_path = default_path
            
            if not map_yaml_path:
                rospy.logwarn(f"⚠️ Could not find map file for coordinate conversion, using coordinates as-is")
                return utm_x, utm_y
            
            # Load map origin
            with open(map_yaml_path, 'r') as f:
                map_config = yaml.safe_load(f)
            
            map_origin = map_config.get('origin', [0.0, 0.0, 0.0])
            
            # Convert UTM to map-relative coordinates
            map_relative_x = utm_x - map_origin[0]
            map_relative_y = utm_y - map_origin[1]
            
            rospy.loginfo(f"🔄 Coordinate conversion:")
            rospy.loginfo(f"   UTM coordinates: ({utm_x:.3f}, {utm_y:.3f})")
            rospy.loginfo(f"   Map origin: ({map_origin[0]:.3f}, {map_origin[1]:.3f})")
            rospy.loginfo(f"   Map-relative coordinates: ({map_relative_x:.3f}, {map_relative_y:.3f})")
            
            return map_relative_x, map_relative_y
            
        except Exception as e:
            rospy.logerr(f"❌ Error converting coordinates: {e}")
            rospy.logwarn(f"⚠️ Using UTM coordinates as-is due to conversion error")
            return utm_x, utm_y
        
    def update_mission_status_backend(self, mission_id, status, executed_time=None, completed_time=None, error_message=None):
        """
        Update mission status in the backend via HTTP PATCH.
        Only the robot should call this.
        """
        backend_url = self.config.get('backend', {}).get('url', 'http://localhost:8000')
        url = f"{backend_url}/api/missions/{mission_id}/status"
        payload = {"status": status}
        if executed_time:
            payload["executedTime"] = executed_time
        if completed_time:
            payload["completedTime"] = completed_time
        if error_message:
            payload["errorMessage"] = error_message
        try:
            resp = requests.patch(url, json=payload, timeout=5)
            resp.raise_for_status()
            rospy.loginfo(f"Mission status updated in backend: {mission_id} -> {status}")
        except Exception as e:
            rospy.logwarn(f"Failed to update mission status in backend: {e}")


if __name__ == '__main__':
    try:
        bridge = FiwareMqttBridge()
        bridge.run()
    except rospy.ROSInterruptException:
        rospy.loginfo("FIWARE MQTT Bridge shutting down")
    except Exception as e:
        rospy.logerr(f"FIWARE MQTT Bridge error: {e}") 