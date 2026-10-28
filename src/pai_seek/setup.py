from glob import glob
from setuptools import setup

package_name = 'pai_seek'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', glob('launch/*.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    license='AGPL-3.0-only',
    entry_points={
        'console_scripts': [
            'detector = pai_seek.detector_node:main',
            'controller = pai_seek.controller_node:main',
            'instruction = pai_seek.instruction_node:main',
            'talk = pai_seek.talk_node:main',
        ],
    },
)
