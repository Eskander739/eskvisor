<meta name="description" content="Eskvisor - open source KVM virtualization management platform with cgroups v2 resource pools, real-time WebSocket task notifications, and automated agent deployment. Lightweight Proxmox alternative.">
<meta name="keywords" content="KVM, libvirt, virtualization, cgroups, resource management, Proxmox alternative, open source, Python, FastAPI, Redis, homelab, self-hosted">

# Eskvisor is a virtualization management project.
![Логотип Eskvisor](./logo.jpg)

⚠️ Status: Proof of concept. Not actively maintained. No enterprise support. Use at your own risk.
⚠️ Only the agent is working correctly and has been tested.
Esquisor is a virtualization management system. The full name is a combination of Esquisor (the developer's identifier) ​​and hypervisor, reflecting the project's primary goal—providing granular control over virtual infrastructure.

### Eskvisor - lightweight KVM management platform with native cgroups v2 resource control and real-time task notifications

## Project structure
```yaml
├───agent # Agent directory for managing the hypervisor on the host side connected to the cluster
│   ├───client # Client directory for working with the hypervisor, models, tests, etc.
│   │   ├───hypervisor # Directory with the main hypervisor codebase
│   │   │   └───libvirt # Directory with managers for interacting with libvirt
│   │   │       ├───managers # Directory with managers for working with virtualization libraries
│   │   │       │   ├───balansir.py # Virtual resource pool manager for CPU and RAM limit control
│   │   │       │   ├───network.py # Manager file for working with virtual networks
│   │   │       │   ├───snapshot.py # Manager file for working with snapshots
│   │   │       │   ├───storage.py # Manager file for working with virtual disks
│   │   │       │   ├───virsh.py # Manager file for establishing connection with guest OS of virtual machine
│   │   │       │   ├───vm.py # Manager file for working with virtual machines
│   │   │       │   └───vm_stats.py # Manager file for live reading of VM state
│   │   │       ├───models # Directory with object models for working with virtualization
│   │   │       │   ├───vm_stats # Directory of models for working with VM statistics retrieval
│   │   │       │   │   └───stats.py # File with VM statistics models
│   │   │       │   ├───volume # Directory of models for working with storages
│   │   │       │   │   ├───balansir.py # File with models of the resource pool manager "Balansir"
│   │   │       │   │   ├───disk.py # File with virtual disk models
│   │   │       │   │   ├───group.py # File with Group Volume models
│   │   │       │   │   ├───logic.py # File with Logic Volume models
│   │   │       │   │   └───physical.py # File with Physical Volume models
│   │   │       │   ├───__init__.py # File turns a regular folder into a Python package
│   │   │       │   ├───controller.py # File with controller models
│   │   │       │   ├───enum.py # File with main enum parameters
│   │   │       │   ├───general.py # File with general models
│   │   │       │   ├───msg.py # File with message models (for manager responses)
│   │   │       │   ├───network.py # File with virtual network models
│   │   │       │   ├───node.py # File with host models
│   │   │       │   ├───snapshots.py # File with snapshot models
│   │   │       │   └───vm.py # File with virtual machine models
│   │   │       ├───client.py # Client file with basic settings for working with the python libvirt library
│   │   │       └───config.py # File with additional configurations
│   │   ├───lvm # Directory with managers for managing Physical Volume, Group Volume, Logic Volume
│   │   │   ├───logical.py # Manager file for managing Logic Volume
│   │   │   ├───physical.py # Manager file for managing Physical Volume
│   │   │   ├───group.py # Manager file for managing Group Volume
│   │   │   └───README.txt # File with a brief description of Physical Volume, Group Volume, Logic Volume operation
│   │   ├───models # Directory with common models for the entire project
│   │   ├───pycgroup # Directory for working with the cgroup v2 resource control system
│   │   │   ├───ctl # Directory for managing cpu, io, memory, pid controllers
│   │   │   │   ├───cpu_ctl.py # Manager file for managing the cpu controller
│   │   │   │   ├───io_ctl.py # Manager file for managing the io controller
│   │   │   │   ├───memory_ctl.py # Manager file for managing the memory controller
│   │   │   │   └───pid_ctl.py # Manager file for managing the pid controller
│   │   │   ├───state # Directory with the cgroup-eskvisor service for restoring and saving the state of resource pools in the cgroup v2 system
│   │   │   │   ├───cgroup-state.service # File with cgroup-state.service for systemd service
│   │   │   │   ├───cgroup-state-timer.timer # File with cgroup-state-timer.timer for systemd service with saving resource pools by timer
│   │   │   │   ├───migrate.sh # Script for migrating cgroup v2 resource pools to the target host
│   │   │   │   ├───README.txt # Examples of running the migrate.sh script
│   │   │   │   ├───restore.sh # Script for restoring resource pools in the cgroup v2 system
│   │   │   │   ├───save.sh # Script for saving resource pools from the cgroup v2 system
│   │   │   │   ├───setup.sh # Script for installing the cgroup-eskvisor service
│   │   │   │   └───verify.sh # Script for checking the status of services and directory of the cgroup-eskvisor service
│   │   │   ├───cgroup_cli.py # Manager file for working with the console for pycgroup
│   │   │   ├───pycgroup.py # Manager file for direct interaction with the pycgroup system
│   │   │   ├───pycgroup_logger.py # File with basic settings for pycgroup logging
│   │   │   └───README.txt # File with a visual description of the cgroup v2 system operation and notes
│   │   ├───stg # Directory with managers for managing external storages
│   │   │   ├───controller.py # Manager file for a broader range of work with NFS storages
│   │   │   └───nfs.py # Manager file for working with NFS storages
│   │   ├───task_manager # Directory with queue manager using Redis
│   │   │   ├───ctl_queue.py # Manager file for managing queues directly in Redis
│   │   │   ├───dispatcher.py # Task dispatcher for managing workers and distributing tasks
│   │   │   ├───models.py # File with queue manager models
│   │   │   ├───worker.py # Manager file with workers (which take tasks from the pool and execute them if there are tasks)
│   │   │   └───ws_notification.py # WebSocket notification handler file
│   │   ├───tests # Directory with the main codebase of autotests
│   │   │   ├───networks # Directory with autotests for virtual networks
│   │   │   ├───resource_containment # Directory with load autotests
│   │   │   ├───resource_pool # Directory with autotests for resource pools
│   │   │   ├───snapshots # Directory with autotests for snapshots
│   │   │   ├───storage # Directory with autotests for virtual disks
│   │   │   ├───system # Directory with autotests for system functions of the agent
│   │   │   ├───virtual_machine # Directory with autotests for virtual machines
│   │   │   ├───__init__.py # File turns a regular folder into a Python package
│   │   │   └───conftest.py # File with autotest fixtures
│   │   ├───__init__.py # File turns a regular folder into a Python package
│   │   ├───cli.py # File for working with the command line
│   │   ├───constants.py # File with main project constants
│   │   ├───logger_config.py # File with basic logging settings
│   │   ├───main.py # File with the backend part of the agent for receiving statistics, receiving and executing tasks, sending notifications during task execution
│   │   └───tools.py # Additional project tools
│   ├───.env # Project configuration file
│   ├───install_agent.sh # Agent installer file
│   ├───nginx.conf # NGINX configuration for the agent
│   └───requirements.txt # File with necessary libraries for agent operation
├───backend # Directory with the backend of the eskvisor project
│   ├───api # Directory with static files of the project landing page
│   │   ├───routers # Directory with API methods
│   │   │   ├───system.py # API for working with system calls
│   │   │   ├───users.py # API for working with users
│   │   │   └───vm.py # API for working with virtual machines
│   │   └───dependencies.py # Dependencies for API
│   ├───src # Directory with source code of the project
│   │   ├───db # Directory for working with databases
│   │   │   └───users.py # Manager file for managing the user database
│   │   ├───models # Directory with project models
│   │   │   ├───agent.py # File with agent models
│   │   │   ├───error.py # File with error models and messages
│   │   │   ├───general.py # File with general models
│   │   │   └───user.py # File with user models
│   │   ├───rbac # Directory with role-based access control models
│   │   │   ├───example_usage.py # File with usage examples
│   │   │   ├───permissions.py # File with permission models
│   │   │   └───roles_and_users.py # File with role and user models
│   │   ├───services # Directory with main project services
│   │   │   ├───hash.py # Manager file for working with hashes
│   │   │   ├───jwt.py # Manager file for working with JWT tokens
│   │   │   ├───redis_srv.py # Manager file for working with Redis
│   │   │   └───ssh_keygen.py # Manager file for generating SSH keys
│   │   ├───tools # Directory with additional tools
│   │   │   └───cli.py # File for working with the command line
│   │   ├───agent_installer.py # Manager file with methods for installing agents on a host
│   │   ├───constants.py # File with constants
│   │   └───logger_config.py # File with basic logging settings
│   ├───.env # Project configuration file
│   ├───main.py # API methods + backend entry point
│   └───requirements.txt # Backend dependencies
├───docs # Directory with main documents
├───landing # Directory of the project landing page
│   ├───app # Directory with static files of the project landing page
│   │   └───templates # Directory with HTML templates
│   │       └───landing.html # Main and only landing page
│   ├───certificate.crt # Landing page certificate for the domain eskvisor.ru
│   ├───certificate.key # Certificate key
│   ├───commands.txt # Commands for deploying the landing page in the cloud
│   ├───main.py # Backend part of the landing page
│   ├───nginx.conf # NGINX configuration for the landing page
│   └───requirements.txt # Python dependencies for the landing page
├───.flake8 # File with flake8 code analyzer configuration
├───.gitconfig # File with Git configuration
├───.gitignore # File for ignoring garbage when working with Git
├───build_test_alpine.txt # Instructions for building all dependencies for agent operation on test alpine linux
├───commands.txt # File with commands for initial project setup
├───LICENSE.md # Project license file
├───logo.jpg # Project logo
├───py_linter.txt # File with linter launch instructions
├───pytest.ini # File for additional pytest configuration
└───README.md # File for describing the project structure, instructions for running autotests, using the agent, etc.
```

#### The backend is unified - the WebSocket Handler is part of the backend, not a separate component.
#### Workers automatically retrieve tasks from the queue (pull model).
#### Dual result retrieval mechanism: push via WebSocket + pull via REST API.I

## RU State registration No. 2026612145
![Логотип Eskvisor](./rospatent.jpg)
