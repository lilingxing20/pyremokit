# pyremokit
Python Remote Toolkit


# Introduction
Pyremokit is a Python-based remote management toolkit. It includes login system execute command line tool cmdsdk, and other features to be supplemented..


# features

  1. login system execute command line tool cmdsdk
  2. other features to be supplemented...

# Installation

## Requirements

  - Python 3.10+

## Install via pip

```
pip install pyremokit
```

# Usage

## 1. login system execute command line tool cmdsdk

### 1.1 Command Line configuration items

  - Login Configuration

    - a) SSH Private Key File Path
      ```
      export PYREMOKIT_DEFAULT_SSHKEY="~/.ssh/id_rsa"
      ```
      > Note: the default private key file path is ~/.ssh/id_rsa.

    - b) SSH Login Timeout
      ```
      export PYREMOKIT_LOGIN_TIMEOUT=10
      ```
      > Note: the default value is 10 seconds.

    - c) Worker Home Path
      ```
      export PYREMOKIT_WORKER_HOME="~/."
      export PRK_WORKER_HOME="~/."
      export WORKER_HOME="~/."
      ```
      > Note: the default worker home path is ~/, and the worker home path can be set by environment variable PYREMOKIT_WORKER_HOME, PRK_WORKER_HOME, or WORKER_HOME.

### 1.2 Execute Command Line Usage

  - Login System

    1) Local command execution
      - [localrunner_01_test01.py](https://github.com/lilingxing20/pyremokit/blob/main/examples/localrunner_01_test01.py)
    2) Login a remote system
      - [pexprunner_01_test01.py](https://github.com/lilingxing20/pyremokit/blob/main/examples/pexprunner_01_test01.py)
    3) Login many remote systems
      - [pexprunner_02_test01.py](https://github.com/lilingxing20/pyremokit/blob/main/examples/pexprunner_02_test01.py)
    4) Login many remote systems with proxy server
      - [pexprunner_03_test01.py](https://github.com/lilingxing20/pyremokit/blob/main/examples/pexprunner_03_test01.py)
    5) Login many remote systems with proxy server and multi-threading
      - [pexprunner_04_test01.py](https://github.com/lilingxing20/pyremokit/blob/main/examples/pexprunner_04_test01.py)

## 2. other features to be supplemented...
