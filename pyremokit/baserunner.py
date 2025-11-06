#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
基础执行类，定义基础方法
'''

import os
import random
import socket
import sys

from collections import OrderedDict

from pyremokit.baseenv import BaseEnv


class BaseRunner():

    def __init__(self, envpointer=None):
        """
        基础执行工具类
        """
        # 如果未指定env，需要执行带参数的connect方法
        if envpointer is None:
            self.env = BaseEnv(parsescript=False)
        else:
            self.env = envpointer

        # 保存执行结果
        self.last_return_code = 0
        self.last_return_msg = ''
        self.last_error_msg = ''
        # 有序字典
        self.cmd_result = OrderedDict()
        self.codedset = ['utf-8', 'gb18030']
        self.tty = {}

    def log(self, logstr, tasklog=True, stdout=True):
        """
        记录日志
        """
        self.env.log(logstr, tasklog=tasklog, stdout=stdout)

    def reply(self, status, code, detail, output=None):
        """
        记录结果
        """
        self.env.reply(status, code, detail, output=output)

    def set_tasklog_end(self):
        """
        脚本任务日志结束描述符
        """
        self.env.set_tasklog_end()

    def report(self, task_progress, task_info, log_type=3, report_url=None, tostdout=False):
        self.env.report(task_progress, task_info, log_type=log_type, report_url=report_url, tostdout=tostdout)

    def report_b64encode(self, task_progress, task_info, log_type=3, report_url=None, tostdout=False):
        self.env.report_b64encode(task_progress, task_info, log_type=log_type, report_url=report_url, tostdout=tostdout)

    def connect(self):
        """
        登陆连接目标主机
        """
        pass

    def close(self):
        """
        断开目标主机连接
        """
        pass

    def get_lastcode(self):
        """
        返回最近一条命令或命令集中最后一条命令的返回值
        一般情况下0值代表成功
        """
        return int(self.last_return_code)

    def get_lastmsg(self):
        """
        返回最近一条命令或命令集中最后一条命令的返回结果
        数据结构为字符串
        """
        return str(self.last_return_msg).strip()

    def get_all_return(self):
        """
        返回所有执行过的命令或命令集的返回结果
        数据结构为有序字典
        """
        return self.cmd_result

    def get_cmd_return(self, cmd_name):
        """
        返回保存在结果集字典中的指定命令的返回结果
        数据结构为字符串
        """
        return self.cmd_result.get(cmd_name, '')

    def reset_result(self, runcmd=False, rundict=False):
        """
        清空命令状态码和结果信息缓存
        """
        self.last_return_code = 0
        self.last_return_msg = ''
        self.last_error_msg = ''
        if rundict:
            self.cmd_result.clear()
        if runcmd:
            self.cmd_result['runcmd'] = []

    def check_param(self,
                    paramname,
                    parameter,
                    genreplyfile=False,
                    currentfile=__file__,
                    currentfun=sys._getframe().f_code.co_name,
                    currentline=sys._getframe().f_lineno
                    ):
        """
        检查参数是否为空
        检查参数是否为空且内容长度是否为0,无返回值
        如果参数非法,动作由 genreplyfile 参数决定
        paramname: 参数名
        parameter: 参数变量
        genreplyfile: 为True表示如果检查非法,记录日志,生成.reply文件后直接退出程序
                如取值为False,当参数非法时抛出一个异常,此异常由上层捕获处理
        以下3个参数直接复制即可
        currentfile=__file__,
        currentfun=sys._getframe().f_code.co_name,
        currentline=sys._getframe().f_lineno
        """
        if not parameter:
            errstr = "The parameter %s value is null!" % paramname
            self.__responerror("-1", errstr, genreplyfile, currentfile, currentfun, currentline)
        # elif len(str(parameter)) == 0:
        #     errstr = "The parameter %s lenth value is 0!" % paramname
        #     return self.__responerror("-1", errstr, genreplyfile, currentfile, currentfun, currentline)

    def __responerror(self,
                      errcode,
                      errstr,
                      genreplyfile=False,
                      currentfile=__file__,
                      currentfun=sys._getframe().f_code.co_name,
                      currentline=sys._getframe().f_lineno
                      ):
        responstr = '[{}][{}()][{}]:[{}],[{}]'.format(currentfile, currentfun,
                                                      currentline, errcode, errstr)
        self.last_return_code = errcode
        self.last_return_msg = responstr
        self.log(responstr)
        if genreplyfile:
            self.reply("FAIL", errcode, responstr)
        else:
            raise Exception(responstr)

    def rundict(self, cmd_dict, onebyone=False, getrtncode=None):
        """
        执行多行命令
        """
        self.check_param('cmd_dict', cmd_dict,
                         genreplyfile=True,
                         currentfile=__file__,
                         currentfun=sys._getframe().f_code.co_name,
                         currentline=sys._getframe().f_lineno
                         )
        self.cmd_result['runcmd'] = []
        for cmd_name, cmd_str in cmd_dict.items():
            self.cmd_result[cmd_name] = cmd_str
        self.last_return_code = 0
        self.last_return_msg = 'base runner run dict success'
        self.last_error_msg = ''
        return self.last_return_code

    def runcmd(self, cmdstr, getrtncode=None):
        """
        执行单行命令
        """
        self.check_param('cmdstr', cmdstr,
                         genreplyfile=True,
                         currentfile=__file__,
                         currentfun=sys._getframe().f_code.co_name,
                         currentline=sys._getframe().f_lineno
                         )
        self.cmd_result['runcmd'] = [cmdstr]
        self.last_return_code = 0
        self.last_return_msg = 'base runner run cmd success'
        self.last_error_msg = ''
        return self.last_return_code

    def suuser(self, su_user, su_pswd):
        """
        切换用户
        """
        self.check_param('su_user', su_user,
                         genreplyfile=True,
                         currentfile=__file__,
                         currentfun=sys._getframe().f_code.co_name,
                         currentline=sys._getframe().f_lineno
                         )
        self.check_param('su_pswd', su_pswd,
                         genreplyfile=True,
                         currentfile=__file__,
                         currentfun=sys._getframe().f_code.co_name,
                         currentline=sys._getframe().f_lineno
                         )

    def isAix(self):
        """
        判断是否 AIX 系统
        """
        res = False
        self.runcmd('uname', getrtncode=False)
        # if str(self.get_cmd_return('runcmd')[-1]).strip().upper() == 'AIX':
        if self.get_lastmsg().upper() == 'AIX':
            res = True
        return res

    def isLinux(self):
        """
        判断是否 LINUX 系统
        """
        res = False
        self.runcmd('uname', getrtncode=False)
        # if str(self.get_cmd_return('runcmd')[-1]).strip().upper() == 'LINUX':
        if self.get_lastmsg().upper() == 'LINUX':
            res = True
        return res

    def isDarwin(self):
        """
        判断是否 DARWIN 系统
        """
        res = False
        self.runcmd('uname', getrtncode=False)
        # if str(self.get_cmd_return('runcmd')[-1]).strip().upper() == 'DARWIN':
        if self.get_lastmsg().upper() == 'DARWIN':
            res = True
        return res

    def get_proxy_port_group(self):
        """
        随机获取代理端口分组
        """
        group_id = random.randint(1, 1000) % self.env.proxy_port_groups
        return self.env.proxy_port_pool[group_id]

    def check_host_port(self, ip="127.0.0.1", port=80, timeout=10):
        """
        检查端口是否使用
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.settimeout(timeout)
            s.connect((ip, int(port)))
            s.shutdown(socket.SHUT_RDWR)
            return True
        except socket.error:
            return False

    def get_available_port(self, start_port=5001, end_port=10000):
        """
        返回一个可用的TCP端口
        """
        port_pool_size = end_port + 1 - start_port
        free_port = None
        for i in range(1, port_pool_size + 1):
            port = start_port + random.randint(1, port_pool_size)
            self.log(f"Try to get free port({port}) for the {i}th time!", tasklog=False)
            if not self.check_host_port(port=port):
                free_port = port
                break
        if not free_port:
            raise Exception("Get free port timeout!")
        return free_port

    def get_ssh_private_keyfile(self):
        """
        指定SSH登陆密钥认证使用的私钥文件路径
        1) 通过环境变量 PYREMOKIT_SSH_PRIVATE_KEYFILE
        2) 默认使用 ~/.ssh/id_rsa
        """
        keyfile = os.getenv("PYREMOKIT_SSH_PRIVATE_KEYFILE") or os.getenv("HOME") + "/.ssh/id_rsa"
        self.log(f"Use ssh private key file: {keyfile}", tasklog=False)
        return keyfile


if __name__ == "__main__":

    br = BaseRunner()
    cmd = 'ls'
    br.runcmd(cmd)
    cmds = OrderedDict()
    cmds['cmd1'] = "ls"
    cmds['cmd2'] = "pwd"
    br.rundict(cmds)

# vi:ts=4:sw=4:expandtab:ft=python:
