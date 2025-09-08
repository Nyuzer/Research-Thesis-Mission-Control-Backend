#!/usr/bin/env python

import rospy
from geometry_msgs.msg import Twist

class CmdVelHandler:
    def __init__(self):
        rospy.init_node('cmd_vel_handler')
        
        # Subscribe to cmd_vel commands from navigation stack
        self.cmd_vel_sub = rospy.Subscriber('/cmd_vel', Twist, self.cmd_vel_callback)
        
        rospy.loginfo("CMD_VEL Handler started - monitoring navigation commands")
        
    def cmd_vel_callback(self, msg):
        """Handle velocity commands from navigation stack"""
        rospy.loginfo("Received cmd_vel: linear.x=%.3f, angular.z=%.3f", 
                     msg.linear.x, msg.angular.z)
        
        # In real robot deployment, this would send commands to robot motors
        # For testing, we just log the commands to verify navigation is working
        
        if abs(msg.linear.x) > 0.01 or abs(msg.angular.z) > 0.01:
            rospy.loginfo("Navigation is commanding robot movement!")
        else:
            rospy.logdebug("Navigation sending zero velocity (stopped)")

if __name__ == '__main__':
    try:
        handler = CmdVelHandler()
        rospy.spin()
    except rospy.ROSInterruptException:
        pass 