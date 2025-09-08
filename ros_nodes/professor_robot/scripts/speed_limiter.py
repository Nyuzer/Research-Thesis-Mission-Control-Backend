#!/usr/bin/env python

import rospy
from geometry_msgs.msg import Twist
import math

class SpeedLimiter:
    def __init__(self):
        rospy.init_node('speed_limiter')
        
        # Get speed scaling parameter (default 20% = 0.2)
        self.speed_scale = rospy.get_param('~speed_scale', 0.2)
        
        # Validate speed scale
        if self.speed_scale <= 0.0 or self.speed_scale > 1.0:
            rospy.logwarn(f"Invalid speed_scale {self.speed_scale}, using default 0.2")
            self.speed_scale = 0.2
        
        # Subscribe to cmd_vel from move_base
        self.cmd_vel_sub = rospy.Subscriber('/cmd_vel', Twist, self.cmd_vel_callback)
        
        # Publish scaled cmd_vel back to the same topic
        self.cmd_vel_pub = rospy.Publisher('/cmd_vel', Twist, queue_size=1)
        
        rospy.loginfo(f"Speed limiter started with {self.speed_scale * 100:.0f}% speed scaling")
        rospy.loginfo("Subscribing to: /cmd_vel")
        rospy.loginfo("Publishing scaled commands to: /cmd_vel")
        
    def cmd_vel_callback(self, msg):
        """Scale incoming velocity commands"""
        try:
            # Create scaled message
            scaled_msg = Twist()
            
            # Scale linear velocities
            scaled_msg.linear.x = msg.linear.x * self.speed_scale
            scaled_msg.linear.y = msg.linear.y * self.speed_scale
            scaled_msg.linear.z = msg.linear.z * self.speed_scale
            
            # Scale angular velocities
            scaled_msg.angular.x = msg.angular.x * self.speed_scale
            scaled_msg.angular.y = msg.angular.y * self.speed_scale
            scaled_msg.angular.z = msg.angular.z * self.speed_scale
            
            # Publish scaled command back to the same topic
            self.cmd_vel_pub.publish(scaled_msg)
            
            # Log significant commands for debugging
            if abs(msg.linear.x) > 0.01 or abs(msg.angular.z) > 0.01:
                rospy.logdebug(f"Speed limit: {msg.linear.x:.3f} → {scaled_msg.linear.x:.3f}, "
                             f"{msg.angular.z:.3f} → {scaled_msg.angular.z:.3f}")
                
        except Exception as e:
            rospy.logerr(f"Error in speed limiter: {e}")

if __name__ == '__main__':
    try:
        limiter = SpeedLimiter()
        rospy.spin()
    except rospy.ROSInterruptException:
        pass 