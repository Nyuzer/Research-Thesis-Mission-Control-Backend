Research Thesis - Mykyta Konakh 7219011

## 1. Required

Before run backend, ros nodes and frontend, you should have:

1. **Ubuntu 20.04** operating system.
2. Install **ROS Noetic**.
3. Installed **python 3**.
4. Installed **node.js** and **npm**.
5. Installed **Docker** and **Docker Compose**
6. **.env** created from a template and located next to **.env-template**

## Preparing the ROS workspace

```
source /opt/ros/noetic/setup.bash

mkdir -p catkin_ws/src
cd catkin_ws

cp -r ros_nodes src/

rosdep update
rosdep install --from-paths src --ignore-src -r -y

catkin_make

source devel/setup.bash
```

## FIWARE Container

```
docker-compose -f docker-compose-robot.yml up -d
```

`P.S.` - Verify that the containers are running:

```
docker-compose -f docker-compose-robot.yml ps
```

## Register robot in the FIWARE:

```
python3 fiware_registration.py
```

## Frontend installation:

```
cd webui && npm install
```

## Launch

1. terminal 1 **Backend**:

```
cd mission_control_backend && ./run_backend.sh
```

2. terminal 2 **ROS Navigation**:

```
source catkin_ws/devel/setup.bash
roslaunch professor_robot navigation.launch
```

3. terminal 3 **ROS Communication**:

```
source catkin_ws/devel/setup.bash
roslaunch fiware_mqtt_bridge fiware_mqtt_bridge.launch
```

4. terminal 4 **Frontend**:

```
cd webui
npm run dev
```

## Structure (expected):

```
project-root/
├─ mission_control_backend/
├─ ros_nodes/
├─ webui/
├─ docker-compose-robot.yml
├─ .env
├─ .env-template
└─ catkin_ws/
```
