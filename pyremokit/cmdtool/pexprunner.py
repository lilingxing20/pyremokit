#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
远程命令执行工具类库: 通过封装pexpect实现远程执行命令并获取执行结果
'''

import os
import re
import sys
import time

from copy import copy
from fcntl import flock
from fcntl import LOCK_EX
from pexpect import EOF
from pexpect import TIMEOUT
from pexpect import runu
from pexpect import spawn
# from pexpect.pxssh import pxssh

from pyremokit.baserunner import BaseRunner
from pyremokit.cmdtool.pexpenv import PexpEnv
from pyremokit.utils.pexpssh import PEXPSSH


__all__ = ['UnitEnv', 'PexpRunner']


class PexpRunner(BaseRunner):
    """
    远程命令执行工具类:
      resetpromt: 是否重置提示符
      getrtncode: 是否获取`echo $?`的值
      注: 当resetpromt为False时，强制将getrtncode设置为False
    """
    def __init__(self,
                 envpointer=None,
                 resetpromt=True,
                 cmdprompt=None,
                 getrtncode=False,
                 explogfile=None,      # 兼容之前逻辑
                 explogtostdout=False,
                 genexpectlog=True,
                 checkpubkey=False,
                 locale=None,
                 timeout=300,
                 login_timeout=30,
                 sync_multiplier=3
                 ):
        """
        PEXPECT 执行工具类
        """
        super().__init__(envpointer)
        # expect timeout
        self.timeout = timeout
        # login timeout
        self.login_timeout = login_timeout
        # sync prompt timout multiplier
        self.sync_multiplier = sync_multiplier

        self.explogtostdout = explogtostdout
        self.genexpectlog = genexpectlog
        self.checkpubkey = checkpubkey
        self.locale = locale

        self.login = {}
        # 如果未指定env，需要执行带参数的connect方法
        if not envpointer:
            self.env = PexpEnv(parsescript=False)
            self.login = self.env.login
        else:
            self.env = envpointer
            self.login = self.env.login
        self.su_param = self.env.su_param

        # 用于执行建立SSH隧道过程中避免端口重用的文件锁
        self.lockfile = self.env.lockfile

        # 解析脚本json参数中的scriptTaskId参数
        self.script_taskid = self.env.script_taskid
        self.explogfile = self.env.expectlog
        self.explogfp = None

        # 兼容之前的逻辑
        if explogfile:
            self.explogfile = explogfile

        # 识别脚本参数中是否交互日志标志: None|True|False
        if self.env.genexpectlog is not None:
            self.genexpectlog = self.env.genexpectlog

        # 多线程另开一个终端读取实时日志时，需要获得正确的工作用户
        self.beensuing = False
        self.suusername = ''
        self.supasswd = ''

        # 如果是主机操作系统，可以支持unset prompt命令，进行联合匹配操作提示符，可以避免如打开一个脚本遇到注释截断的尴尬
        # 如果是网络设备，则使用基本的#$>进行操作提示符匹配
        # 是否有联合匹配会导致结果返回数组最末一行不同，需要处理
        self.resetpromt = resetpromt
        if self.resetpromt is False:
            self.getrtncode = False
        else:
            self.getrtncode = getrtncode

        # 设定提示符
        # self.original_prompt = r"[$#>]"
        self.original_prompt = r"[\S]*[$#>][\s]{0,1}"
        self.cmdprompt = cmdprompt or self.original_prompt

        # SSH Terminal
        self.cmdclient = None

        # 记录是否连接远程主机
        self.connected = False
        self.is_console = False

        # 记录SSH转发终端信息
        self.proxy_ssh_tunnels = []

        # ssh 配置项
        self.ssh_options = {}
        # self.protocol 兼容性赋值
        self.protocol = 'SSH_PSWD'

    def expect_logfile_open(self):
        """
        打开expect交互式日志
          - 标准输出
          - 日志文件
        """
        if self.genexpectlog:
            if not self.explogfp:
                if self.explogtostdout:
                    # 交互日志打印到标准输出
                    self.explogfp = sys.stdout
                    self.log("Expect log to stdout", tasklog=False)
                else:
                    # 交互日志打印到日志文件
                    self.explogfp = open(self.explogfile, 'a+', encoding="utf8")
                    self.log(f'Open expect log file: {self.explogfile}', tasklog=False)
        else:
            # 禁用交互日志
            self.explogfp = None

    def expect_logfile_close(self):
        """
        关闭expect日志文件
        """
        if self.genexpectlog:
            if self.explogfp:
                self.explogfp.close()
                self.explogfp = None

    def expect_logfile_delete(self):
        """
        删除expect日志文件
        """
        if self.explogfile:
            if os.path.exists(self.explogfile):
                os.remove(self.explogfile)

    def make_ssh_options(self):
        """
        ssh配置项
        """
        if not self.checkpubkey:
            self.ssh_options = {
                "IPQoS": "throughput",
                "ServerAliveInterval": "60",
                "StrictHostKeyChecking": "no",
                "UserKnownHostsFile": "/dev/null"
            }

    def create_terminal(self):
        """
        创建 SSH Terminal
        """
        self.expect_logfile_open()
        self.make_ssh_options()
        # python3中对文件编码更严格了，因此必须指定spawn使用的字符集
        # sshclient = pxssh(logfile=self.explogfp,
        sshclient = PEXPSSH(logfile=self.explogfp,
                            timeout=self.timeout,
                            options=self.ssh_options,
                            encoding='utf-8',
                            # 命令回显: False关闭, True开启(默认)
                            echo=True,
                            maxread=50000)
        if self.resetpromt:
            self.cmdprompt = sshclient.PROMPT
        else:
            sshclient.PROMPT = self.cmdprompt
        self.log('SSH terminal created.')
        return sshclient

    def set_locale_lc_all(self, locale=None):
        """
        设置系统字符集（临时生效）
        Linux: en_US.UTF-8
        Aix: en_US
        """
        _locale = locale or self.locale
        if _locale:
            self.cmdclient.set_locale_lc_all(locale)

    def set_system_env(self):
        """
        设置系统Terminal环境（临时生效）
        """
        self.cmdclient.set_system_env()

    def get_win_size(self):
        """
        查看窗口大小
        """
        return self.cmdclient.getwinsize()

    def set_win_size(self, row=24, col=256):
        """
        设置窗口大小
        ushort format requires 0 <= row <= (32767 *2 +1)
        ushort format requires 0 <= col <= (32767 *2 +1)
        """
        self.cmdclient.setwinsize(int(row), int(col))

    def set_win_col_size_maxread(self):
        """
        命令行窗口宽度默认值为80个字符
        maxread属性设置读取缓冲区大小, 即pexpect每次尝试从tty读取的最大字节数
        设置命令行窗口宽度为读取缓冲区大小
        """
        self.cmdclient.setwinsize(24, self.cmdclient.maxread)

    def check_and_resize_win(self, cmd_len):
        """
        检查命令长度并调整终端窗口宽度
        """
        # len("[PEXPECT]#") == 10
        cmd_col = cmd_len + len(self.cmdclient.PROMPT)
        row, col = self.get_win_size()
        if col < cmd_col:
            self.set_win_size(row, cmd_col)

    def first_connect_change_passwd(self, new_password):
        """
        首次连接主机根据提示修改密码
        """
        if not new_password:
            raise Exception("The new_password parameter is null!")

        # 创建 SSH Terminal
        self.cmdclient = self.create_terminal()

        rtn = self.cmdclient.first_login_change_passwd(
            self.login['ip'],
            port=self.login['port'],
            username=self.login['username'],
            password=self.login['password'],
            new_password=new_password,
            login_timeout=self.login_timeout,
            sync_multiplier=self.sync_multiplier
        )
        if rtn is True:
            self.log('Modify the password of host %s user %s successfully.' % (
                self.login['ip'], self.login['host_user']))
        else:
            raise TIMEOUT('Unable to connect to host!')
        return rtn

    def create_ssh_tunnel(self, tunnel_type, ssh_tunnel, proxy_info):
        """
        建立SSH隧道
        tunnel_type: local/remote/dynamic
        ssh_tunnel: "{bind_ip}:{bind_port}:{host_ip}:{host_port}"
        tunnel_type: dynamic
        ssh_tunnel: "{bind_ip}:{bind_port}"
        """
        # 创建 SSH Terminal
        cmdclient = self.create_terminal()
        ssh_tunnels = {tunnel_type: [ssh_tunnel]}
        try:
            if str(proxy_info['authMode']).upper() in set(['SSH_KEY', "KEY"]):
                keyfile = proxy_info['password'] or self.get_ssh_private_keyfile()
                cmdclient.options["PreferredAuthentications"] = "publickey"
                rtn = cmdclient.login(proxy_info['ip'],
                                      port=int(proxy_info['port']),
                                      username=proxy_info['username'],
                                      ssh_key=keyfile,
                                      ssh_tunnels=ssh_tunnels,
                                      original_prompt=self.original_prompt,
                                      auto_prompt_reset=self.resetpromt,
                                      login_timeout=self.login_timeout,
                                      sync_original_prompt=False
                                      )
                if rtn is True:
                    self.log('SSH terminal start.')
                    self.log("SSH link has been established. " +
                             " host:" + proxy_info['ip'] +
                             " port:" + str(proxy_info['port']) +
                             " user:" + proxy_info['username']
                             )
                else:
                    raise TIMEOUT('Unable to connect to proxy host(%s)!' % proxy_info['ip'])

            elif str(proxy_info['authMode']).upper() in set(['SSH_PSWD', "PASSWORD"]):
                cmdclient.options["PreferredAuthentications"] = "password"
                rtn = cmdclient.login(proxy_info['ip'],
                                      port=int(proxy_info['port']),
                                      username=proxy_info['username'],
                                      password=proxy_info['password'],
                                      ssh_tunnels=ssh_tunnels,
                                      original_prompt=self.original_prompt,
                                      auto_prompt_reset=self.resetpromt,
                                      login_timeout=self.login_timeout,
                                      sync_original_prompt=False
                                      )
                if rtn is True:
                    self.log('SSH terminal start.')
                    self.log("SSH link has been established. " +
                             " host:" + proxy_info['ip'] +
                             " port:" + str(proxy_info['port']) +
                             " user:" + proxy_info['username']
                             )
                else:
                    raise TIMEOUT('Unable to connect to proxy host(%s)!' % proxy_info['ip'])
            else:
                raise Exception('The authMode(%s) is unknown!' % proxy_info['authMode'])

        except Exception as e:
            exp_info = "Exception info: [" + str(e) + "] when connect to " + \
                       " host:" + proxy_info['ip'] + \
                       " port:" + str(proxy_info['port']) + \
                       " user:" + proxy_info['username']
            self.last_return_msg = exp_info
            self.log(exp_info)
            return self.last_return_msg
        return cmdclient

    def make_local_tunnel(self, bind_ip="127.0.0.1"):
        """
        建立正向SSH隧道
        """
        proxy_list = self.login.get("hostProxyList", [])
        proxy_num = len(proxy_list)
        for i in range(proxy_num):
            # 获取代理端口池
            proxy_pg = self.get_proxy_port_group()
            lockfile = proxy_pg["lockfile"]
            start_port, end_port = proxy_pg['pool']
            # 创建文件锁, 避免建立SSH隧道时端口重用问题
            with open(lockfile, "a+", encoding='utf-8') as fp:
                # 给文件加锁, 并且这里如果检查到已加锁, 进程会被阻塞等待
                flock(fp.fileno(), LOCK_EX)
                proxy_info = copy(proxy_list[i])
                bind_port = self.get_available_port(start_port, end_port)
                fp.write(str(bind_port) + ",")
                if i == proxy_num - 1:
                    # 最后一个proxy主机
                    host_ip = self.login['ip']
                    host_port = self.login['port']
                    self.login['host_proxy_ip'] = bind_ip
                    self.login['host_proxy_port'] = bind_port
                else:
                    host_ip = proxy_list[i + 1]['ip']
                    host_port = proxy_list[i + 1]['port']
                ssh_tunnel = ":".join([bind_ip, str(bind_port), host_ip, str(host_port)])

                # 多个proxy时的第一个
                if not self.proxy_ssh_tunnels:
                    pass
                # 多个proxy时的中间
                else:
                    proxy_info['ip'] = self.proxy_ssh_tunnels[-1]['bind_ip']
                    proxy_info['port'] = self.proxy_ssh_tunnels[-1]['bind_port']

                # 创建本地转发端口
                self.log("Create ssh tunnel: %s" % ssh_tunnel)
                cmdclient = self.create_ssh_tunnel("local", ssh_tunnel, proxy_info)
                self.proxy_ssh_tunnels.append({
                    "ssh_tunnel": ssh_tunnel,
                    "bind_ip": bind_ip,
                    "bind_port": bind_port,
                    "proxy_info": proxy_info,
                    "cmdclient": cmdclient
                })

    def _connect(self):
        """
        连接远程主机
        """
        # 创建 SSH Terminal
        self.cmdclient = self.create_terminal()

        try:
            _auth_mode = str(self.login['authMode']).upper()
            _host_ip = self.login.get('host_proxy_ip') or self.login['ip']
            _host_port = self.login.get("host_proxy_port") or self.login['port']
            _host_user = self.login['username']
            _host_pswd_or_key = self.login['password']

            # 测试网络端口是否可连接
            if not self.check_host_port(ip=_host_ip, port=_host_port, timeout=self.login_timeout):
                self.last_return_code = -2
                raise Exception("Network port not available !")

            # 登录
            try:
                if _auth_mode in set(['SSH_KEY', "KEY"]):
                    keyfile = _host_pswd_or_key or self.get_ssh_private_keyfile()
                    self.cmdclient.options["PreferredAuthentications"] = "publickey"
                    rtn = self.cmdclient.login(_host_ip,
                                               port=_host_port,
                                               username=_host_user,
                                               ssh_key=keyfile,
                                               original_prompt=self.original_prompt,
                                               auto_prompt_reset=self.resetpromt,
                                               login_timeout=self.login_timeout,
                                               sync_multiplier=self.sync_multiplier
                                               )
                    if rtn is True:
                        self.log('SSH terminal start.')
                        self.log("SSH link has been established. " +
                                 " host:" + _host_ip +
                                 " port:" + str(_host_port) +
                                 " user:" + _host_user
                                 )
                        # set system sh env.
                        self.set_system_env()
                        # set locale LC_ALL.
                        self.set_locale_lc_all()
                    else:
                        raise TIMEOUT('Unable to connect to host(%s)!' % _host_ip)

                elif _auth_mode in set(['SSH_PSWD', "PASSWORD"]):
                    # self.cmdclient.force_password = True
                    self.cmdclient.options["PreferredAuthentications"] = "password"
                    rtn = self.cmdclient.login(_host_ip,
                                               port=_host_port,
                                               username=_host_user,
                                               password=_host_pswd_or_key,
                                               original_prompt=self.original_prompt,
                                               auto_prompt_reset=self.resetpromt,
                                               login_timeout=self.login_timeout,
                                               sync_multiplier=self.sync_multiplier
                                               )
                    if rtn is True:
                        self.log('SSH terminal start.')
                        self.log("SSH link has been established." +
                                 " host:" + _host_ip +
                                 " port:" + str(_host_port) +
                                 " user:" + _host_user
                                 )
                        # set system sh env.
                        self.set_system_env()
                        # set locale LC_ALL.
                        self.set_locale_lc_all()
                    else:
                        raise TIMEOUT('Unable to connect to host(%s)!' % _host_ip)

                else:
                    raise Exception('The authMode(%s) is unknown !' % _auth_mode)

            except Exception as e:
                self.last_return_code = -1
                raise Exception("Login failed: " + str(e)) from e

            # 登陆成功
            self.last_return_code = 0
            self.last_return_msg = "login success"
            self.connected = True

        except Exception as e:
            exp_info = "Exception info: [" + str(e) + "] when connect to " + \
                       " host:" + self.login['ip'] + \
                       " port:" + str(self.login['port']) + \
                       " user:" + self.login['username']
            self.last_return_msg = exp_info
            self.last_return_code = self.last_return_code or -3
            self.log(exp_info)

        return self.last_return_code

    # def connect_withparam(self, auth_mode, ip, port, user, pswdorkey):
    def connect_withparam(self, ip, port, auth_mode, user, pswdorkey):
        """
        指定参数连接远程主机
        """
        self.login['authMode'] = auth_mode
        self.login['ip'] = ip
        self.login['port'] = port
        self.login['username'] = user
        self.login['password'] = pswdorkey
        return self.connect()

    def connect_lpar_console(self):
        """
        连接远程主机
        """
        managed_host = self.login['lpar']['managedHost']
        lpar_name = self.login['lpar']['lparName']
        lpar_user = self.login['lpar']['username']
        lpar_pswd = self.login['lpar']['password']
        ret = self.cmdclient.login_console(managed_host, lpar_name, lpar_user, lpar_pswd)
        if ret:
            self.is_console = True
            # We appear to be in.
            # set shell prompt to something unique.
            if self.resetpromt:
                self.cmdclient.auto_set_unique_prompt()
            # set system sh env.
            self.set_system_env()
            # set locale LC_ALL.
            self.set_locale_lc_all()
        else:
            self.close()
            raise Exception(f'Failed to login lpar{lpar_name} console!')
        return 0

    def connect(self, login=None, idx=0, is_reconnect=False):
        """
        连接远程主机
        """
        ret = 0
        if self.connected:
            # 已连接
            ret = 0
        else:
            if login:
                self.login = login
            elif idx and self.env.login_list:
                self.login = self.env.login_list[idx]
            # 未连接
            if self.login.get("hostProxyList"):
                self.make_local_tunnel()
            ret = self._connect()
            # 连接成功
            if ret == 0:
                if self.login.get("lpar"):
                    # 登录Lpar控制台
                    ret = self.connect_lpar_console()
                if not is_reconnect:
                    # 切换用户
                    if self.su_param:
                        self.suuser(self.su_param['username'], self.su_param['password'])
                elif self.beensuing:
                    # 异常断开重连后，并恢复已切换用户
                    self.suuser(self.suusername, self.supasswd)
        return ret

    def close(self):
        """
        关闭远程连接
        """
        try:
            # 防止连接已被意外关闭
            if self.is_console:
                self.cmdclient.logout_console()
                self.log("Logout lpar console.")
            elif self.connected:
                self.cmdclient.sendline("exit")
                index = self.cmdclient.expect([self.cmdprompt,
                                               "(?i)there are stopped jobs",
                                               "y/n",
                                               "yes/no",
                                               "(?i)Unrecognized command found at",
                                               EOF])
                if index == 0:
                    # 嵌套了su
                    self.cmdclient.sendline("exit")
                    self.cmdclient.expect([self.cmdprompt, TIMEOUT, EOF])
                elif index == 1:
                    self.cmdclient.sendline("exit")
                    self.cmdclient.expect([self.cmdprompt, TIMEOUT, EOF])
                elif index == 2:
                    self.cmdclient.sendline("y")
                    self.cmdclient.expect([self.cmdprompt, TIMEOUT, EOF])
                elif index == 3:
                    self.cmdclient.sendline("yes")
                    self.cmdclient.expect([self.cmdprompt, TIMEOUT, EOF])
                elif index == 4:
                    # 华为交换机退出用quit
                    self.cmdclient.sendline("quit")
                    self.cmdclient.expect([self.cmdprompt, TIMEOUT, EOF])
                elif index == 5:
                    self.log("SSH link closed.")
            else:
                self.log("SSH link not created.")
            # 关闭ssh终端
            if self.cmdclient:
                self.cmdclient.close()
            self.log("SSH terminal exit.")
        except Exception as e:
            self.log("SSH close tty exception: %s" % str(e))

        finally:
            self.connected = False
            self.is_console = False
            self.expect_logfile_close()

        # 关闭ssh隧道终端
        try:
            for proxy_ssh_tunnel in self.proxy_ssh_tunnels:
                if proxy_ssh_tunnel.get('cmdclient'):
                    proxy_ssh_tunnel['cmdclient'].close()
        except Exception as e:
            self.log("SSH close tunnel tty exception: %s" % str(e))

    def reconnect(self):
        """
        重新连接远程主机
        """
        self.close()
        return self.connect(is_reconnect=True)

    def suuser(self, su_user, su_pswd):
        """
        切换登录用户
        """
        # 执行新的命令之前清空状态码和结果信息缓存
        self.reset_result(runcmd=True)
        # 执行新的命令之前清空pexpect的回显缓存
        self.reset_prompt()

        self.runcmd('whoami', getrtncode=False)
        userbeforsu = self.cmd_result['runcmd']
        # Note: ['root', 'You have new mail in /var/spool/mail/root']
        if su_user in set(userbeforsu):
            self.log('The same user does not execute su!')
            self.last_return_code = 0
            return self.last_return_code

        # 开始切换用户
        self.cmdclient.sendline('su - ' + su_user)
        if "root" not in set(userbeforsu):
            if self.cmdclient.expect(['(?i)Password:', 'does not exist', TIMEOUT]) == 0:
                # 输入密码
                self.cmdclient.sendline(su_pswd)
            else:
                self.last_return_code = -2  # 用户切换错误
                self.last_return_msg = self.cmdclient.before
                self.log(self.last_return_msg)
                # 此处close是为了防止外部未判断返回值的情况下继续执行命令
                self.close()
                raise EOF('Authentication failed for su - ' + su_user + ' !')

        # 检查用户切换是否成功
        index = self.cmdclient.expect([self.original_prompt, TIMEOUT, EOF], timeout=10)
        buff = self.cmdclient.before
        if index == 0:
            # 如果有提示密码错误的信息，直接走错误逻辑
            if buff.find('Authentication is denied') == -1 and \
                    buff.find('Authentication failure') == -1 and \
                    buff.find('incorrect password') == -1 and \
                    buff.find('鉴定故障') == -1 and \
                    buff.find('sorry') == -1:
                # 未匹配到任何已知错误输出的情况下，再做一次whoami验证，确保已正确完成su
                self.cmdclient.sendline('whoami')
                i = self.cmdclient.expect([self.original_prompt, TIMEOUT, EOF])
                if i == 0:  # 此处的超时可能是要求修改密码的提示阻断，视为失败
                    if self.cmdclient.before.find(su_user) != -1:
                        if self.resetpromt:
                            # set shell prompt to something unique.
                            self.cmdclient.auto_set_unique_prompt()
                        # set system sh env.
                        self.set_system_env()
                        # set locale LC_ALL.
                        self.set_locale_lc_all()

                        self.last_return_code = 0
                        self.beensuing = True
                        self.suusername = su_user
                        self.supasswd = su_pswd
                        self.log('su - ' + su_user + ' successful!')
                    else:
                        raise Exception(f'Current user is not {su_user} !')
                else:
                    raise TIMEOUT('Check current username timeout !')
            else:
                self.last_return_code = -2  # 密码错误
                self.last_return_msg = buff
                self.log(self.last_return_msg)
                # 此处close是为了防止外部未判断返回值的情况下继续执行命令
                self.close()
                raise EOF('Authentication failed for su - ' + su_user + ' !')
        else:
            raise TIMEOUT('Check su result timeout')
        return self.last_return_code

    def sulogout(self):
        """
        切换退出用户
        """
        # 简单操作
        if self.beensuing:
            self.runcmd('exit', getrtncode=False)
            self.beensuing = False
            self.suusername = ''
            self.supasswd = ''
        # 安全操作
        # self.runcmd('whoami', getrtncode=False)
        # curruser = self.cmd_result['runcmd'][-1]
        # if self.suusername and curruser == self.suusername:
        #     self.runcmd('exit', getrtncode=False)
        #     self.runcmd('whoami', getrtncode=False)
        #     curruser = self.cmd_result['runcmd']
        #     if curruser != self.suusername:
        #         self.beensuing = False
        #         self.suusername = ''
        #         self.supasswd = ''

    def reset_prompt(self):
        """
        清空pexpect的回显缓存
        """
        while self.expect_prompt_timeout(timeout=1):
            pass
        self.cmdclient.buffer = ''
        self.cmdclient.before = ''
        self.cmdclient.after = ''

    def readbuffer(self, rcvstr, resplist, cmdstr=None, cmdlist=None, updatelastmsg=True):
        """
        读取命令执行结果
        删除命令本身的回显
        """
        # 保存命令输出结果
        tmpstr = rcvstr

        # 读取所有缓存
        # 匹配到的提示符之前的内容
        before = self.cmdclient.before
        # 匹配到的提示符之后的内容
        # buffer = self.cmdclient.buffer
        # 匹配到的提示符
        # after = self.cmdclient.after
        # tmpstr = tmpstr + before + buffer
        tmpstr = tmpstr + before
        # 持续读去buffer中的内容,直到prompt超时
        read_buffer_times = 1
        while self.runner_prompt(timeout=0.1):
            read_buffer_times += 1
            tmpstr = tmpstr + self.cmdclient.before
        self.log('Read data from buffer times: %s' % read_buffer_times, tasklog=False)

        # 多次回车试探tty中是否还有未读取数据,直到连续prompt超时4次
        read_data_times = 0
        read_null_times = 0
        read_null_data = False
        while True:
            read_data_times += 1
            self.cmdclient.sendline()
            rpstat = self.runner_prompt()
            # rpstat = self.expect_prompt_timeout()
            rtn = self.cmdclient.before
            if rpstat:
                if str(rtn).strip():
                    tmpstr = tmpstr + rtn
                    read_null_times = 0
                    read_null_data = False
                else:
                    read_null_times += 1
                    read_null_data = True
            else:
                msg = f'Runner prompt timeout({self.timeout}) when running command: {rtn}'
                resplist.append(msg)
                raise Exception(msg)
            if read_null_data and read_null_times > 3:
                break
        self.log('Read data from TTY times: %s' % read_data_times, tasklog=False)

        # fix-2024-01-21: 发现在AIX系统执行包含'_'的命令回显时,会在'_'前面会多出' \x08'字符
        #   eg: ls aaa___bbb---ccc
        #       ls aaa \x08_ \x08_ \x08_bbb--ccc
        #       aaa___bbb--cc not found
        # ASCII 控制字符的十六进制范围在 00 到 1F 和 7F 的字符
        # re.sub(r"[\x00-\x1F\x7F]", "", text)
        # 处理掉控制字符
        tmpstr = re.sub(r" [\x00-\x1F\x7F]_", "_", tmpstr)

        # 处理掉cmd回显
        if cmdstr:
            # tmpstr = tmpstr.replace(cmdstr + self.cmdclient.crlf, '').strip()
            tmpstr = re.sub(r'\b' + re.escape(cmdstr) + r'\b', '', tmpstr)
        if cmdlist and isinstance(cmdlist, list):
            for _cmdstr in cmdlist:
                # tmpstr = tmpstr.replace(_cmdstr + self.cmdclient.crlf, '').strip()
                # tmpstr = re.sub(r'\b' + re.escape(_cmdstr) + r'\b', '', tmpstr)
                tmpstr = re.sub(r'\b' + re.escape(_cmdstr) + r'\r\n', '', tmpstr)

        # 当执行setwinsize会出现清除从光标到行尾的内容的特殊符号(\x1b[K)
        tmpstr = tmpstr.replace("\x1b[K", '').strip()

        # 将接收的有效数据逐行append到resplist
        for item in tmpstr.splitlines(False):
            item = str(item).strip()
            if len(item) > 0:
                # 检查结果行字符串是否有命令行提示符
                # 1) re.match()方法要求必须从字符串的开头进行匹配
                # 2) re.search()会扫描整个字符串查找匹配
                if not re.match(self.cmdprompt, item, flags=0):
                    resplist.append(item)
                else:
                    # 当回显内容或返回值与提示符混到同一行拿到时，要处理这种情况
                    item = re.sub(self.cmdprompt, "", item)
                    if len(item) > 0:
                        resplist.append(item)

        # 将接收的所有数据以字符串形式写入self.last_return_msg
        if updatelastmsg is True:
            self.last_return_msg = tmpstr

    def runner_prompt(self, timeout=None):
        """
        True表示正常返回控制台，False说明执行的命令一直占据控制时间未返回到控制台
        """
        if not timeout:
            timeout = self.timeout
        session_expect = [self.cmdprompt,
                          # 1
                          '(?i)Are you sure to quit',
                          # 2
                          '(?i)press any key to',
                          # 3
                          '(?i)nohup: ignoring input and appending output to',
                          # 4
                          '(?i)confirmation required yes/no',
                          # 5
                          "(?i)Has 'rootpre.sh' been run by root in this machine?",
                          # 6
                          "(?i)Do you want me to remove these directories",
                          # 7
                          "PYREMOKIT-TAIL-END-FLAG",
                          # 8
                          TIMEOUT,
                          # 9
                          EOF]
        i = self.cmdclient.expect(session_expect, timeout=timeout)
        if i == 0:
            return True
        if i == 1:
            # Are you sure to quit
            return self.send_answer_cmd('y', timeout)
        if i == 2:
            # 执行的命令回显有明确提示键入任意字符以显示下一屏时，发送一个回车
            return self.send_answer_cmd('', timeout)
        if i == 3:
            # 调用的脚本中使用了nohup方式执行其它脚本，需要发送一个回车
            return self.send_answer_cmd('', timeout)
        if i == 4:
            # Aix 系统中 vmo命令修改系统参数 Modification to restricted tunable maxperm%, confirmation required yes/no
            return self.send_answer_cmd('yes', timeout)
        if i == 5:
            # oracle安装脚本里的提示 Has 'rootpre.sh' been run by root in this machine? [y/n] (n)
            return self.send_answer_cmd('y', timeout)
        if i == 6:
            # Aix系统中 snap -r 命令: Do you want me to remove these directories (y/n)?
            return self.send_answer_cmd('y', timeout)
        if i == 7:
            # 调用的脚本中使用tail -f 命令打开日志，遇到约定退出标志时，需要发送 ctrl+c 结束操作
            return self.send_control_cmd('c', timeout)
        if i in (8, 9):
            return False

    def expect_prompt_timeout(self, timeout=None):
        """
        匹配终端提示符返回True
        超时返回False
        """
        if not timeout:
            timeout = self.timeout
        i = self.cmdclient.expect([self.cmdprompt, TIMEOUT], timeout=timeout)
        if i == 1:
            return False
        return True

    def send_enter(self, timeout=None):
        """
        向终端发送回车
        """
        if not timeout:
            timeout = self.timeout
        self.cmdclient.sendline()
        return self.expect_prompt_timeout(timeout)

    def runner_prompt_agent(self):
        """
        向终端发送一次回车
        """
        self.cmdclient.sendline()
        return self.runner_prompt()

    def send_control_cmd(self, cmd="c", timeout=None):
        """
        向终端发送控制命令: ctl+<cmd>
        """
        if not timeout:
            timeout = self.timeout
        self.cmdclient.sendcontrol(cmd)
        res = None
        if self.protocol in ('SSH_KEY', 'SSH_PSWD'):
            res = self.cmdclient.prompt()
        else:
            res = self.expect_prompt_timeout(timeout)
        return res

    def send_answer_cmd(self, cmd="", timeout=None):
        """
        向终端发送应答命令: yes/no/y/n
        """
        if not timeout:
            timeout = self.timeout
        self.cmdclient.sendline(cmd)
        res = None
        if self.protocol in ('SSH_KEY', 'SSH_PSWD'):
            res = self.runner_prompt()
        else:
            res = self.expect_prompt_timeout(timeout)
        return res

    def runcmd(self, cmdstr, getrtncode=None):
        """
        执行单个命令
          - 执行之前先connect()
          - 支持上下文,支持交互
          - 当getrtncode值设置为False时, 则检查命令的返回值(echo $?), 非0为失败
          - 当getrtncode值设置为False时, 则不检查命令的返回值(echo $?)
          - 注意在非主机操作系统环境下, getrtncode必须为False.
        """
        cmdstr = str(cmdstr).strip()
        # self.checkparam('cmdstr', cmdstr,
        #                 genreplyfile=True,
        #                 currentfile=__file__,
        #                 currentfun=sys._getframe().f_code.co_name,
        #                 currentline=sys._getframe().f_lineno
        #                 )

        # 服务器闪断的判断
        if self.cmdclient.isalive():
            self.cmdclient.sendline()
        if self.connected is True and not self.cmdclient.isalive():
            self.log("SSH 连接异常断开!")
            self.reconnect()

        # 判断是否连接服务器
        if not self.connected:
            self.last_return_msg = 'Please connect the remote host or device first!'
            self.last_return_code = -1
            self.log(self.last_return_msg)
            return self.last_return_code

        # 执行新的命令之前清空状态码和结果信息缓存
        self.reset_result(runcmd=True)
        # 执行新的命令之前清空pexpect的回显缓存
        self.reset_prompt()

        # 是否获取命令执行退出码:$?
        if getrtncode is None:
            _getrtncode = self.getrtncode
        else:
            _getrtncode = getrtncode

        try:
            self.log('Run remote cmd: [' + cmdstr + ']')
            if not cmdstr:
                self.cmdclient.sendline()
                _getrtncode = False
            else:
                self.cmdclient.sendline(cmdstr)

            ret = self.runner_prompt()
            if ret is False or ret is None:
                self.last_return_code = 99
                self.last_return_msg = 'The operation timed out and the connection was disconnected.'
                self.log(self.last_return_msg)
                return self.last_return_code

            # 获得返回后发送两次回车判断是否有被操作提示符匹配而隔断的内容
            self.cmd_result['runcmd'] = []
            self.readbuffer(self.last_return_msg, self.cmd_result['runcmd'], cmdstr=cmdstr)
            # self.log('Return msg: [\n' + '\n'.join(self.cmd_result['runcmd']) + '\n]')
            self.log('Return msg: %s' % self.cmd_result['runcmd'])

            # 获取命令执行退出状态码
            if _getrtncode is True and len(cmdstr) != 0:

                # 执行新的命令之前清空pexpect的回显缓存
                self.reset_prompt()

                _cmdstr = "echo $?"
                self.log('Check cmd exit code: [' + _cmdstr + ']')
                self.cmdclient.sendline(_cmdstr)
                ret = self.runner_prompt()
                while not ret:
                    self.cmdclient.sendline()
                    ret = self.runner_prompt()

                # 不能覆盖之前已取到的命令结果信息: self.last_return_msg
                _resps = []
                self.readbuffer("", _resps, cmdstr=_cmdstr, updatelastmsg=False)
                if len(_resps) <= 0:
                    self.last_return_code = -3
                    self.log('$? code: No return value was obtained.')
                else:
                    # 防止返回值不位于最后一行导致类型转化错误
                    retcode = None
                    for line in reversed(_resps):
                        _line = str(line).strip()
                        if _line.isdigit():
                            retcode = int(_line)
                            break
                    if retcode is None:
                        self.log('$? code: Could not get the return value of integer type!')
                        self.last_return_code = -4
                    else:
                        self.last_return_code = retcode
                self.log('Return code: %s' % self.last_return_code)
            else:
                self.last_return_code = 0

        except Exception as e:
            self.last_return_code = 99
            self.last_return_msg = str(e)
            self.log(self.last_return_msg)

        return self.last_return_code

    def rundict(self, cmd_dict, onebyone=False, getrtncode=None):
        """
        执行多个命令
          - 支持 逐条命令提交执行 与 批量提交执行 两种模式
          - 逐条模式相当于for循环调用runcmd
          - 批量模式一般用于执行第一条命令后进入另一个控制台的场景,例如sqlplus，无法获取每条命令的单独返回值
          - 批量模式下不能有出现再次判断之类的互动，否则需要使用runner_prompt方法
          - 批量模式时务必保证所有命令提交后能回到控制台，像su之后一定要exit；进入sqlplus之后一定要quit
        """
        # self.checkparam('cmd_dict', cmd_dict,
        #                 genreplyfile=True,
        #                 currentfile=__file__,
        #                 currentfun=sys._getframe().f_code.co_name,
        #                 currentline=sys._getframe().f_lineno
        #                 )

        # 服务器闪断的判断
        if self.connected is True and not self.cmdclient.isalive():
            self.reconnect()

        # 判断是否连接服务器
        if not self.connected:
            self.last_return_msg = 'Please connect the remote host or device first!'
            self.last_return_code = -1
            self.log(self.last_return_msg)
            return self.last_return_code

        # 执行新的命令之前清空状态码和结果信息缓存
        self.reset_result(rundict=True)
        # 执行新的命令之前清空pexpect的回显缓存
        self.reset_prompt()

        try:
            if onebyone is True:
                # 逐条
                for cmdname in cmd_dict:
                    cmd = cmd_dict[cmdname]
                    self.runcmd(cmd, getrtncode=getrtncode)
                    # 如果有失败的执行记录，则退出不继续执行剩余
                    if self.get_lastcode() == 0:
                        # self.cmd_result[cmdname] = self.get_lastmsg()
                        self.cmd_result[cmdname] = self.cmd_result['runcmd']
                    else:
                        break
            else:
                # 批量
                cmdlist = []
                for cmdname in cmd_dict:
                    cmd = str(cmd_dict[cmdname]).strip()
                    self.log('Run remote cmd: [' + cmd + ']')
                    if not cmd:
                        self.cmdclient.sendline()
                    else:
                        cmdlist.append(cmd)
                        self.cmdclient.sendline(cmd)
                    # 命令发送后等待时间
                    wait_sec = 0.1
                    m_ret = re.match(r".*-WAIT-(\d+)", cmdname)
                    if m_ret:
                        wait_sec = int(m_ret.groups()[0])
                    time.sleep(wait_sec)

                # 批量命令列表为空时发送一个回车
                if not cmd_dict:
                    self.cmdclient.sendline()
                # 等待命令执行
                time.sleep(0.1 * len(cmdlist))
                # 批量执行几行命令,就需要prompt成功几次
                ret = self.runner_prompt()
                if ret is False or ret is None:
                    self.last_return_code = 99
                    self.last_return_msg = 'The executed command or script did not exit to the console and timed out waiting.'
                    self.log(self.last_return_msg)
                    return self.last_return_code

                # 获得返回后连续发送回车判断是否有被操作提示符匹配而隔断的内容
                self.cmd_result['runcmd'] = []
                self.readbuffer(self.last_return_msg, self.cmd_result['runcmd'], cmdlist=cmdlist)
                # self.log('Return msg: [\n' + '\n'.join(self.cmd_result['runcmd']) + '\n]')
                self.log('Return msg: %s' % self.cmd_result['runcmd'])

        except Exception as e:
            self.last_return_code = 99
            self.last_return_msg = str(e)
            self.log(self.last_return_msg)

        return self.last_return_code

    def runlocal_once(self, command, timeout=30, withexitstatus=False, events=None,
                      extra_args=None, logfile=None, cwd=None, env=None, **kwargs):
        """
        运行本地命令
        """
        self.log('Run local cmd: [ ' + command + ' ]')
        rtn = runu(command, timeout=timeout, withexitstatus=withexitstatus, events=None,
                   extra_args=None, logfile=None, cwd=None, env=None, **kwargs)
        if withexitstatus:
            self.last_return_code = rtn[1]
            self.log('Return code: [' + str(self.last_return_code) + ']')
            self.last_return_msg = rtn[0].strip()
            self.cmd_result['runcmd'] = self.last_return_msg
            # self.log('Return msg: [\n' + self.last_return_msg + '\n]')
            self.log('Return msg: %s' % self.cmd_result['runcmd'])
        else:
            self.log('Return code not detected.')
            self.last_return_msg = rtn.strip()
            self.cmd_result['runcmd'] = self.last_return_msg
            # self.log('Return msg: [\n' + self.last_return_msg + '\n]')
            self.log('Return msg: %s' % self.cmd_result['runcmd'])
        return rtn

    def __responerror(self, errcode, errstr,
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
        raise Exception(responstr)

    def checkparam(self, paramname, parameter,
                   genreplyfile=False,
                   currentfile=__file__,
                   currentfun=sys._getframe().f_code.co_name,
                   currentline=sys._getframe().f_lineno
                   ):
        if not parameter:
            errstr = "The parameter %s value is null!" % paramname
            self.__responerror("-1", errstr, genreplyfile, currentfile, currentfun, currentline)
        if len(str(parameter)) == 0:
            errstr = "The parameter %s lenth value is 0!" % paramname
            self.__responerror("-1", errstr, genreplyfile, currentfile, currentfun, currentline)

    def scp_upload(self, local_file, remote_file, remote_ip, remote_user, remote_pswd, remote_port=22, timeout=1800):
        ssh_options = {
            "RSAAuthentication": "no",
            "PubkeyAuthentication": "no",
            "StrictHostKeyChecking": "no",
            "UserKnownHostsFile": "/dev/null"
        }
        options = ''.join([" -o '%s=%s'" % (o, v) for (o, v) in ssh_options.items()])
        scp_cmd = 'scp -rp %s -P %s %s %s@%s:%s' % (options, remote_port, local_file, remote_user, remote_ip, remote_file)
        self.log('Run local cmd: [' + scp_cmd + ']')
        self.expect_logfile_open()
        ssh = spawn(scp_cmd,
                    logfile=self.explogfp,
                    encoding='utf-8',
                    # 命令回显: False关闭, True开启(默认)
                    echo=True,
                    timeout=timeout,
                    maxread=5000)
        r = ""
        try:
            i = ssh.expect(['password: ', 'continue connecting (yes/no)?'])
            if i == 0:
                ssh.sendline(remote_pswd)
            elif i == 1:
                ssh.sendline('yes')
                ssh.expect('password:')
                ssh.sendline(remote_pswd)
            r = ssh.read()
            ssh.expect(EOF)
            ssh.close()
        except EOF:
            ssh.close()
        except Exception as ex:
            r = ex
        r = r.strip().replace('\r\n', '\n').replace('\r', '\n')
        self.log('Return msg: %s' % r)
        return r

    def scp_download(self, remote_file, local_file, remote_ip, remote_user, remote_pswd, remote_port=22, timeout=1800):
        ssh_options = {
            "RSAAuthentication": "no",
            "PubkeyAuthentication": "no",
            "StrictHostKeyChecking": "no",
            "UserKnownHostsFile": "/dev/null"
        }
        options = ''.join([" -o '%s=%s'" % (o, v) for (o, v) in ssh_options.items()])
        scp_cmd = 'scp -rp %s -P %s %s@%s:%s %s' % (options, remote_port, remote_user, remote_ip, remote_file, local_file)
        self.log('Run local cmd: [' + scp_cmd + ']')
        self.expect_logfile_open()
        ssh = spawn(scp_cmd,
                    logfile=self.explogfp,
                    encoding='utf-8',
                    # 命令回显: False关闭, True开启(默认)
                    echo=True,
                    timeout=timeout,
                    maxread=5000)
        r = ""
        try:
            i = ssh.expect(['password: ', 'continue connecting (yes/no)?'])
            if i == 0:
                ssh.sendline(remote_pswd)
            elif i == 1:
                ssh.sendline('yes')
                ssh.expect('password:')
                ssh.sendline(remote_pswd)
            r = ssh.read()
            ssh.expect(EOF)
            ssh.close()
        except EOF:
            ssh.close()
        except Exception as ex:
            r = ex
        r = r.strip().replace('\r\n', '\n').replace('\r', '\n')
        self.log('Return msg: %s' % r)
        return r

# vi:ts=4:sw=4:expandtab:ft=python:
