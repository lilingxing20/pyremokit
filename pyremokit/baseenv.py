#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
基础环境初始化
'''

import json
import os
import platform
import sys
import threading
import time

from base64 import b64encode
from collections import OrderedDict
from datetime import datetime

import requests

from pyremokit.utils.aes_gcm import AESGCMCipher


# 防止多线程同时写同一文件
g_threadloglock = threading.RLock()


FORM_PARAMETER = set(['note', 'shortNote', 'required', 'valueType'])
NON_BUSI_PARAMETER = set(['note', 'shortNote', 'required', 'valueType',
                          'login', "loginWinRM", 'loginOracle', 'loginMySQL', 'loginDM', 'loginMsSQL',
                          'suUser', 'scriptTaskId', 'scriptLogPath',
                          'genTaskLog', 'genReplyLog', 'genExpectLog'])
LOGIN_PARAMETER = set(['login', "loginWinRM", 'loginOracle', 'loginMySQL', "loginDM", "loginMsSQL"])
ENCRYPTION_PARAMETER_KEY = set(["password"])


def str_to_bool(flag):
    """
    bool -> bool
    str -> bool
    """
    ret = False
    if isinstance(flag, bool):
        ret = flag
    elif isinstance(flag, str):
        if flag.upper() in set(["Y", "YES", "T", "TRUE"]):
            ret = True
        elif flag.upper() in set(["N", "NO", "F", "FALSE"]):
            ret = False
    else:
        raise Exception("The value is invalid !")
    return ret


def decrypt_encrypted_params(data):
    """
    遍历脚本输入参数，对所有 ENCRYPTION_PARAMETER_KEY 参数进行解密尝试
    1) 如果解密成功更新为解密后的值
    2) 如果解密失败保持原始输入的值
    """
    if isinstance(data, dict):
        for key, val in data.items():
            if isinstance(val, (dict, list)):
                decrypt_encrypted_params(val)
            if key in ENCRYPTION_PARAMETER_KEY:
                data[key] = AESGCMCipher.aes_gcm_decrypt(val)
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, (dict, list)):
                decrypt_encrypted_params(item)


class BaseEnv():
    """
    基础环境准备
    """

    def __init__(self,
                 checkparams=True,
                 parsescript=True,
                 logpath=None,
                 logfile=None,
                 printtostdout=False,
                 genreplylog=False,
                 gentasklog=False):
        """
        参数检查并格式化
        """
        self.check_python_version()
        self.printtostdout = printtostdout
        self.genreplylog = genreplylog
        self.gentasklog = gentasklog
        self.genexpectlog = None
        self.genprogresslog = None
        self.decrypt_encrypted_parameter = str_to_bool(os.getenv("PYREMOKIT_DECRYPT_ENCRYPTED_PARAMETER", "False"))
        self.cmdline = ""

        # 当前平台的行终止符
        #   - Windows使用'\r\n'
        #   - Linux使用'\n'
        #   - Mac使用'\r'
        self.linesep = os.linesep
        self.win_linesep = '\r\n'
        self.linux_linesep = '\n'
        self.mac_linesep = '\r'
        # 当前操作系统的路径分隔符
        self.sep = os.sep

        # 脚本输入参数
        self.params_json = {}
        # 查询结果信息
        self.result_inspection = {}

        # 参数整理
        self.login = {}
        self.su_param = {}
        self.parameter = {}
        self.script_taskid = None
        self.script_logpath = None

        # 获取脚本参数
        # - argv[0] 当前脚本名称
        # - argv[1] 脚本业务参数
        # - argv[2] 脚本任务名称
        argc = len(sys.argv)
        if argc < 2:
            raise Exception("Script parameters are missing !")
        argv = []
        for index in range(0, argc):
            argv.append(sys.argv[index])
            if self.cmdline:
                self.cmdline = self.cmdline + " '" + str(sys.argv[index]) + "'"
            else:
                self.cmdline = str(sys.argv[index])

        # 获取脚本目录和文件名 argv[0]
        self.scriptrealfile = os.path.realpath(argv[0])
        self.scriptpath, self.scriptname = os.path.split(self.scriptrealfile)

        # 获取脚本业务参数 argv[1]
        self.script_parameter = argv[1]
        # 解析脚本输入参数，转化成 JSON 对象
        self.parse_script_input_param()

        if argc > 2:
            self.script_taskid = str(argv[2])

        for k, v in self.params_json.items():
            if k in FORM_PARAMETER:
                continue
            if k in LOGIN_PARAMETER:
                self.login = v
            elif k == "suUser":
                self.su_param = v
            elif k == "scriptTaskId":
                self.script_taskid = v
            elif k == "scriptLogPath":
                self.script_logpath = v
            elif k == "genTaskLog":
                self.gentasklog = str_to_bool(v)
            elif k == "genReplyLog":
                self.genreplylog = str_to_bool(v)
            elif k == "genExpectLog":
                self.genexpectlog = str_to_bool(v)
            elif k == "genProgressLog":
                self.genprogresslog = str_to_bool(v)
            elif k == "decryptEncryptedParameter":
                self.decrypt_encrypted_parameter = str_to_bool(v)
            else:
                self.parameter[k] = v

        # 脚本日志目录
        env_logpath = os.getenv("PYREMOKIT_SCRIPT_LOG_PATH")
        if self.script_logpath:
            self.logpath = str(self.script_logpath).strip().rstrip(self.sep)
        elif logpath:
            self.logpath = str(logpath).strip().rstrip(self.sep)
        elif env_logpath:
            self.logpath = str(env_logpath).strip().rstrip(self.sep)
        else:
            self.logpath = self.scriptpath + self.sep + "log"
        # 脚本日志文件
        if logfile:
            self.logfile = self.logpath + self.sep + logfile
        else:
            today = time.strftime("%Y-%m-%d", time.localtime())
            self.logfile = self.logpath + self.sep + "script_" + str(today) + ".log"

        # 创建脚本日志目录
        self.workhome = self.logpath
        if not os.path.exists(self.logpath):
            os.makedirs(self.logpath, mode=0o755, exist_ok=True)

        if self.script_taskid:
            self.replylog = self.logpath + self.sep + self.script_taskid + ".repy.log"
            self.tasklog = self.logpath + self.sep + self.script_taskid + ".task.log"
            self.expectlog = self.logpath + self.sep + self.script_taskid + ".expect.log"
            self.progresslog = self.logpath + self.sep + self.script_taskid + ".progress.log"
        else:
            timenow = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            self.replylog = self.logpath + self.sep + str(timenow) + ".reply.log"
            self.tasklog = self.logpath + self.sep + str(timenow) + ".task.log"
            self.expectlog = self.logpath + self.sep + str(timenow) + ".expect.log"
            self.progresslog = self.logpath + self.sep + str(timenow) + ".progress.log"

        # 用于执行建立SSH隧道过程中避免端口重用的文件锁
        self.lockpath = self.logpath + "/.filelock/"
        if not os.path.exists(self.lockpath):
            os.makedirs(self.lockpath, mode=0o755, exist_ok=True)
        self.lockfile = self.lockpath + '/pexp.lock'
        self.proxy_port_pool = {}
        self.proxy_port_start = 5000
        self.proxy_port_end = 10000
        self.proxy_port_groups = 50
        self.proxy_port_group_size = int((self.proxy_port_end - self.proxy_port_start) / self.proxy_port_groups)
        for i in range(1, self.proxy_port_groups + 1):
            self.proxy_port_pool[i] = {"lockfile": self.lockpath + f'/pexp_{i}.lock',
                                       "pool": (5000 + (i - 1) * self.proxy_port_group_size + 1,
                                                5000 + i * self.proxy_port_group_size)
                                       }

        # 解密已加密的脚本参数
        self.decrypt_encrypted_script_param()

    def check_python_version(self):
        """
        检查当前python的 主版本 和 次版本
        """
        major_ver, minor_ver, _ = platform.python_version_tuple()
        if int(major_ver) < 3 or (int(major_ver) == 3 and int(minor_ver) < 6):
            raise Exception("Current python version %s is less than 3.6 !" % platform.python_version())

    def parse_script_input_param(self):
        """
        解析脚本输入参数
        脚本参数: BaseEnv.script_parameter
        """
        paramstr = self.script_parameter
        try:
            self.params_json = json.loads(paramstr)
        except Exception as e:
            raise Exception(f'Cannot convert string {paramstr} to JSON! [{e}]') from e
        return self.params_json

    def decrypt_encrypted_script_param(self):
        """
        遍历脚本输入参数，对已加密的脚本参数进行解密
        """
        if self.decrypt_encrypted_parameter:
            try:
                decrypt_encrypted_params(self.params_json)
            except Exception as e:
                raise Exception(f"decrypt encrypted script param exception: {str(e)}") from e

    def log(self, logstr, tasklog=True, stdout=True):
        """
        记录执行日志
        """
        if g_threadloglock.acquire():
            # log_time = time.strftime("%Y-%m-%d_%H:%M:%S", time.localtime()),
            # log_time = datetime.now().isoformat(),  # eg: 2023-07-11T11:21:27.864211
            log_time = datetime.now().strftime('%Y-%m-%d_%H:%M:%S.%f')
            log_line = '%s %s %s %s - %s' % (
                log_time,
                self.scriptname,
                os.getpid(),
                self.script_taskid,
                logstr
            )
            with open(self.logfile, 'a+', encoding='utf-8') as log_fp:
                log_fp.write(log_line)
                log_fp.write(self.linesep)
            # 记录任务日志
            if self.gentasklog and tasklog:
                tasklog_line = '%s %s - %s' % (
                    log_time,
                    self.script_taskid,
                    logstr
                )
                with open(self.tasklog, 'a+', encoding='utf-8') as log_fp:
                    log_fp.write(tasklog_line)
                    log_fp.write(self.linesep)
            # 日志打印到标准输出
            if self.printtostdout and stdout:
                print(log_line)
            g_threadloglock.release()

    def reply(self, status, code, detail, output=None):
        """
        status: SUCCESS|FAIL|TIMEOUT|STOP
        code: 0|-1
        detail: description words
        output: only used when script type is INSPECTION or COMPLIANCE
        """
        drpreply = OrderedDict()
        drpreply['status'] = str(status)
        drpreply['code'] = str(code)
        drpreply['detail'] = str(detail)
        if output:
            drpreply['output'] = output
        elif self.result_inspection:
            drpreply['output'] = self.result_inspection

        replystr = json.dumps(drpreply, ensure_ascii=False, default=str)

        # 结束前写任务日志通知后台日志输出结束
        self.log(f"CMD: {self.cmdline}, OUT: {replystr}", tasklog=False)
        if self.genreplylog:
            with open(self.replylog, 'w+', encoding='utf-8') as log_fp:
                log_fp.write(replystr)
                log_fp.write(self.linesep)
                if self.linesep != "\n":
                    # 防止java写死'\n'
                    log_fp.write('\n')

    def progress(self, logstr):
        """
        记录脚本运行进度信息
        """
        if self.genprogresslog:
            if g_threadloglock.acquire():
                with open(self.progresslog, 'a+', encoding='utf-8') as log_fp:
                    log_fp.write(logstr)
                    log_fp.write(self.linesep)
                g_threadloglock.release()

    def set_tasklog_end(self):
        """
        脚本任务日志结束描述符
        EXPLOGEND--<scriptTaskId>--EXPLOGEND
        """
        taskendstr = f"TASKLOGEND--{self.script_taskid}--TASKLOGEND"
        # 设置任务日志结束描述符
        if self.gentasklog:
            with open(self.tasklog, 'a+', encoding='utf-8') as log_fp:
                log_fp.write(taskendstr)
                log_fp.write(self.linesep)
                if self.linesep != "\n":
                    # 防止java写死'\n'
                    log_fp.write('\n')
        if self.genprogresslog:
            with open(self.progresslog, 'a+', encoding='utf-8') as log_fp:
                log_fp.write(taskendstr)
                log_fp.write(self.linesep)
                if self.linesep != "\n":
                    # 防止java写死'\n'
                    log_fp.write('\n')

    def report(self, task_progress, task_info, log_type=3, report_url=None, tostdout=False):
        """
        上报运行进度信息
        """
        data = {
            "logTime": self.get_ymdhmsf(),
            "logType": str(log_type),
            "taskProgress": str(round(task_progress, 2)),
            "taskInfo": str(task_info)
        }
        data = json.dumps(data, ensure_ascii=False, default=str)
        self.log("Report log info: " + str(task_info), tasklog=False)

        # 记录进度日志
        if self.genprogresslog:
            self.progress(data)

        # 标准输出打印
        if tostdout:
            now_str = self.get_ymdhmsf()
            progress = "%6.2f%%" % round(task_progress, 2)
            print(f"{now_str} [{progress}] {task_info}")

        # 回调接口上报进度日志
        if str(report_url).startswith('http'):
            headers = {
                "accept": "application/json",
                "Content-Type": "application/json",
            }
            response = requests.post(report_url, headers=headers, data=data.encode('utf-8'), timeout=5)
            self.log("Post URL result: " + response.text)

    def report_b64encode(self, task_progress, task_info, log_type=3, report_url=None, tostdout=False):
        """
        上报运行进度信息
        log_type:
          - 1: 仅更新 进度
          - 2: 仅更新 日志
          - 3: 同时更新 进度 和 日志
        """
        task_info_b64 = b64encode(task_info.encode('utf-8'))
        self.report(task_progress, str(task_info_b64).split("'")[1],
                    log_type=log_type, report_url=report_url, tostdout=tostdout)

    def get_ymdhms(self):
        """
        当前日期时间: 年-月-日 时:分:秒
        """
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    def get_ymdhmsf(self):
        """
        当前日期时间: 年-月-日_时:分:秒.毫秒
        """
        return datetime.now().strftime('%Y-%m-%d_%H:%M:%S.%f')

# vi:ts=4:sw=4:expandtab:ft=python:
