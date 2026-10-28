from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    target = LaunchConfiguration('target')
    mode = LaunchConfiguration('mode')
    return LaunchDescription([
        DeclareLaunchArgument('target', default_value='person'),
        DeclareLaunchArgument('mode', default_value='follow'),   # follow / approach / stop
        Node(package='pai_seek', executable='detector', output='screen'),
        Node(package='pai_seek', executable='controller', output='screen',
             parameters=[{'target': target, 'mode': mode}]),
        Node(package='pai_seek', executable='instruction', output='screen'),
    ])
