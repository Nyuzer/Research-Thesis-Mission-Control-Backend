#!/usr/bin/env python

import rospy
import math
from std_msgs.msg import String
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus
from sensor_msgs.msg import NavSatFix
from nav_msgs.msg import Odometry

class GnssDiagnostics:
    """
    Production GNSS Diagnostics and Health Monitoring
    
    Monitors:
    - GNSS signal quality and accuracy
    - Fix type and satellite count
    - Position accuracy and stability
    - System health and alerts
    """
    
    def __init__(self):
        rospy.init_node('gnss_diagnostics')
        
        # Diagnostic state
        self.last_fix = None
        self.last_odom = None
        self.position_history = []
        self.accuracy_history = []
        
        # Health metrics
        self.fix_rate = 0.0
        self.position_stability = 0.0
        self.accuracy_trend = "STABLE"
        
        # Subscribers
        self.fix_sub = rospy.Subscriber('/fix', NavSatFix, self.fix_callback)
        self.odom_sub = rospy.Subscriber('/gnss/odometry', Odometry, self.odom_callback)
        self.status_sub = rospy.Subscriber('/gnss/status', String, self.status_callback)
        
        # Publishers
        self.health_pub = rospy.Publisher('/gnss/health', String, queue_size=1)
        
        # Timer for diagnostics
        self.diag_timer = rospy.Timer(rospy.Duration(5.0), self.publish_health)
        
        rospy.loginfo("🔍 GNSS Diagnostics monitoring started")
    
    def fix_callback(self, msg):
        self.last_fix = msg
        
        # Track accuracy
        if len(msg.position_covariance) >= 9:
            accuracy = math.sqrt(msg.position_covariance[0] + msg.position_covariance[4])
            self.accuracy_history.append(accuracy)
            if len(self.accuracy_history) > 20:
                self.accuracy_history.pop(0)
    
    def odom_callback(self, msg):
        self.last_odom = msg
        
        # Track position stability
        pos = [msg.pose.pose.position.x, msg.pose.pose.position.y]
        self.position_history.append(pos)
        if len(self.position_history) > 10:
            self.position_history.pop(0)
    
    def status_callback(self, msg):
        # Parse status message
        status_parts = msg.data.split(',')
        for part in status_parts:
            if part.startswith('ACC:'):
                try:
                    accuracy = float(part.split(':')[1])
                    self.current_accuracy = accuracy
                except:
                    pass
    
    def calculate_position_stability(self):
        if len(self.position_history) < 5:
            return 0.0
        
        # Calculate standard deviation of recent positions
        positions = self.position_history[-5:]
        x_coords = [pos[0] for pos in positions]
        y_coords = [pos[1] for pos in positions]
        
        x_std = math.sqrt(sum([(x - sum(x_coords)/len(x_coords))**2 for x in x_coords]) / len(x_coords))
        y_std = math.sqrt(sum([(y - sum(y_coords)/len(y_coords))**2 for y in y_coords]) / len(y_coords))
        
        return math.sqrt(x_std**2 + y_std**2)
    
    def analyze_accuracy_trend(self):
        if len(self.accuracy_history) < 10:
            return "INSUFFICIENT_DATA"
        
        recent = self.accuracy_history[-5:]
        older = self.accuracy_history[-10:-5]
        
        recent_avg = sum(recent) / len(recent)
        older_avg = sum(older) / len(older)
        
        if recent_avg < older_avg * 0.9:
            return "IMPROVING"
        elif recent_avg > older_avg * 1.1:
            return "DEGRADING"
        else:
            return "STABLE"
    
    def publish_health(self, event):
        if not self.last_fix:
            return
        
        # Calculate metrics
        self.position_stability = self.calculate_position_stability()
        self.accuracy_trend = self.analyze_accuracy_trend()
        
        # Determine overall health
        health_level = "HEALTHY"
        health_msg = []
        
        # Check accuracy
        if hasattr(self, 'current_accuracy'):
            if self.current_accuracy > 2.0:
                health_level = "WARNING"
                health_msg.append(f"Accuracy degraded: {self.current_accuracy:.1f}m")
            elif self.current_accuracy > 5.0:
                health_level = "ERROR"
                health_msg.append(f"Poor accuracy: {self.current_accuracy:.1f}m")
        
        # Check position stability
        if self.position_stability > 1.0:
            health_level = "WARNING"
            health_msg.append(f"Position unstable: {self.position_stability:.2f}m std")
        
        # Check fix status
        if self.last_fix.status.status < 0:
            health_level = "ERROR"
            health_msg.append("No GPS fix")
        
        # Publish health message
        health_str = f"GNSS:{health_level}"
        if health_msg:
            health_str += f" - {', '.join(health_msg)}"
        
        health_ros_msg = String()
        health_ros_msg.data = health_str
        self.health_pub.publish(health_ros_msg)
        
        rospy.loginfo_throttle(30, f"🔍 GNSS Health: {health_str}")

if __name__ == '__main__':
    try:
        diagnostics = GnssDiagnostics()
        rospy.spin()
    except rospy.ROSInterruptException:
        rospy.loginfo("🔍 GNSS Diagnostics shutting down") 