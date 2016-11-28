===========
Environment
===========

1. Install Tendrl node agent (https://github.com/Tendrl/node_agent)
2. Install Etcd>=2.3.x && <3.x (https://github.com/coreos/etcd/releases/tag/v2.3.7)


============
Installation
============

Since there is no stable release yet, the only option is to install the project
from the source.

Development version from the source
-----------------------------------

1. Install http://github.com/tendrl/common from the source code::

    $ git clone https://github.com/Tendrl/common.git
    $ cd common
    $ mkvirtualenv performance_monitoring
    $ pip install .

2. Create common logging config file::

    $ cp etc/samples/logging.yaml.timedrotation.sample /etc/tendrl/performance_monitoring_logging.yaml

Note that there are other sample config files for logging shipped with the product
and could be utilized for logging differently. For example there are config files
bundeled for syslog and journald logging as well. These could be used similarly as above.

3. Install performance monitoring itself::

    $ git clone https://github.com/Tendrl/performance_monitoring.git
    $ cd performance_monitoring
    $ workon performance_monitoring
    $ pip install .

Note that we use virtualenvwrapper_ here to activate ``performance_monitoring`` `python
virtual enviroment`_. This way, we install *performance monitoring* into the same virtual
enviroment which we have created during installation of *integration common*.

.. _virtualenvwrapper: https://virtualenvwrapper.readthedocs.io/en/latest/
.. _`python virtual enviroment`: https://virtualenv.pypa.io/en/stable/

4. Create config file::

    $ cp etc/tendrl/tendrl.conf.sample /etc/tendrl/tendrl.conf
    $ cp etc/logging.yaml.timedrotation.sample /etc/tendrl/performance_monitoring_logging.yaml

5. Edit ``/etc/tendrl/tendrl.conf`` as below

    Set the value of ``log_cfg_path`` under section ``common``

    ``log_cfg_path = /etc/tendrl/common_logging.yaml``

    Set the value of ``log_cfg_path`` under section ``performance_monitoring``

    ``log_cfg_path = /etc/tendrl/performance_monitoring_logging.yaml``


6. Create log dir::

    $ mkdir /var/log/tendrl/common
    $ mkdir /var/log/tendrl/performance_monitoring

7. Run::

    $ tendrl-performance-monitoring
