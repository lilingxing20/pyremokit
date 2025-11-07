#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
远程命令执行工具类库: 通过封装pexpect实现远程执行命令并获取执行结果
'''

from base64 import b64encode
from copy import copy
from fcntl import flock
from fcntl import LOCK_EX

import socket
import socks
from pexpect import TIMEOUT

from winrm import Response
from winrm import Session
from winrm.protocol import Protocol

from pyremokit.baserunner import BaseRunner
from pyremokit.cmdtool.wrmenv import WrmEnv
from pyremokit.utils.pexpssh import PEXPSSH


__all__ = ['WrmEnv', 'WrmRunner']

# setting utf-8(65001), default us_en(437), zh_cn(936)
LANGUAGE_ENCODING_DICT = {
    "UTF-8": "UFT-8",
    "US_EN": "ASCII",
    "ZH_CN": "GBK"
}
LANGUAGE_CODEPAGE_DICT = {
    "UTF-8": 65001,
    "US_EN": 437,
    "ZH_CN": 936
}
CODEPAGE_LANGUAGE_DICT = {
    "65001": "UFT-8",
    "437": "US_EN",
    "936": "ZH_CN"
}


class WrmRunner(BaseRunner, Session):
    """
    Windows远程命令执行工具类:
      执行CMD命令
      执行PowerShell命令
    """
    def __init__(self,
                 envpointer=None,
                 codepage="UTF-8",
                 encoding="UTF-8",
                 checkpubkey=False,
                 timeout=300,
                 login_timeout=30
                 ):
        """
        Windows CMD/PowerShell 执行工具类
        """
        super().__init__(envpointer)
        # BaseRunner.__init__(self, envpointer)
        # expect timeout
        self.timeout = timeout
        # login timeout
        self.login_timeout = login_timeout

        self.codepage = codepage.upper()
        self.encoding = encoding.upper()

        self.checkpubkey = checkpubkey

        self.login = {}
        # 如果未指定env，需要执行带参数的connect方法
        if envpointer is None:
            self.env = WrmEnv(parsescript=False)
        else:
            self.env = envpointer
        self.login = self.env.login

        # 用于执行建立SSH隧道过程中避免端口重用的文件锁
        self.lockfile = self.env.lockfile

        # 解析脚本json参数中的scriptTaskId参数
        self.script_taskid = self.env.script_taskid
        self.explogfile = self.env.expectlog
        self.explogfp = None

        # 记录是否连接远程主机
        self.connected = False
        self.shell_id = None
        self.protocol = None

        # 记录SSH转发终端信息
        self.proxy_ssh_tunnels = []

        # ssh 配置项
        self.ssh_options = {}

    def open_shell(self):
        """
        open shell
        codepage: utf-8(65001)
                  default us_en(437)
                  zh_cn(936)
        """
        # TODO optimize perf. Do not call open/close shell every time
        if not self.shell_id:
            codepage = LANGUAGE_CODEPAGE_DICT.get(self.codepage, 65001)
            self.shell_id = self.protocol.open_shell(codepage=codepage)

    def close_shell(self):
        """
        close shell
        """
        if self.shell_id:
            self.protocol.close_shell(self.shell_id)
            self.shell_id = None
        self.connected = False

    def get_shell_active_codepage(self):
        """
        显示活动代码页
        """
        self.runcmd("chcp")
        self.log("Show shell %s active codepage %s" % (self.shell_id, self.get_lastmsg()))

    def set_shell_active_codepage(self, codepage=None):
        """
        设置活动代码页
        """
        # 字符集
        if codepage:
            _codepage = LANGUAGE_CODEPAGE_DICT.get(self.codepage, 65001)
        else:
            _codepage = LANGUAGE_CODEPAGE_DICT.get(codepage, 65001)
        self.runcmd('chcp %s' % _codepage)
        self.log("Set shell %s active codepage %s result: %s" % (self.shell_id, codepage, self.get_lastmsg()))

    def _connect(self, transport='ntlm'):
        """
        connect remote host
        """
        try:
            scheme = self.login.get('scheme', "http")
            host_ip = self.login['ip']
            host_port = self.login['port']
            host_user = self.login['username']
            host_password = self.login['password']
            target = "%s://%s:%s" % (scheme, host_ip, host_port)

            # 测试网络端口是否可连接
            if not self.check_host_port(ip=host_ip, port=host_port):
                self.last_return_code = -2
                raise Exception("Network port not available !")

            # 建立连接
            try:
                # build url
                url = self._build_url(target, transport)
                # connect
                self.protocol = Protocol(url,
                                         username=host_user,
                                         password=host_password,
                                         transport=transport
                                         )
                # open shell
                self.open_shell()
                # show shell active codepage
                self.get_shell_active_codepage()

            except Exception as e:
                self.last_return_code = -1
                raise Exception(f"Connect failed: {e}") from e

            # 连接成功
            self.last_return_code = 0
            self.last_return_msg = "Connect success"
            self.connected = True

        except Exception as e:
            exp_info = "Exception info: [" + str(e) + "] when connect to " + \
                       " ip:" + self.login['ip'] + \
                       " port:" + str(self.login['port']) + \
                       " user:" + self.login['username']
            self.last_return_msg = exp_info
            self.last_return_code = self.last_return_code or -3
            self.log(exp_info)

        return self.last_return_code

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
        self.make_ssh_options()
        # python3中对文件编码更严格了，因此必须指定spawn使用的字符集
        # sshclient = pxssh(logfile=None,
        sshclient = PEXPSSH(logfile=None,
                            timeout=self.timeout,
                            options=self.ssh_options,
                            encoding='utf-8',
                            # 命令回显: False关闭, True开启(默认)
                            echo=True,
                            maxread=50000)
        self.log('SSH terminal created.')
        return sshclient

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
                                      original_prompt=r"[$#>]",
                                      auto_prompt_reset=False,
                                      login_timeout=self.login_timeout,
                                      sync_original_prompt=False
                                      )
                if rtn is True:
                    self.log('SSH terminal start.')
                    self.log("SSH link has been established. " +
                             " host:" + proxy_info['ip'] +
                             " port:" + str(proxy_info['port']) +
                             " username:" + proxy_info['username']
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
                                      original_prompt=r"[$#>\]]",
                                      auto_prompt_reset=False,
                                      login_timeout=self.login_timeout,
                                      sync_original_prompt=False
                                      )
                if rtn is True:
                    self.log('SSH terminal start.')
                    self.log("SSH link has been established. " +
                             " host:" + proxy_info['ip'] +
                             " port:" + str(proxy_info['port']) +
                             " username:" + proxy_info['username']
                             )
                else:
                    raise TIMEOUT('Unable to connect to proxy host(%s)!' % proxy_info['ip'])
            else:
                raise Exception('The authMode(%s) is unknown!' % proxy_info['authMode'])

        except Exception as e:
            exp_info = "Exception info: [" + str(e) + "] when connect to " + \
                       " host:" + proxy_info['ip'] + \
                       " port:" + str(proxy_info['port']) + \
                       " username:" + proxy_info['username']
            self.last_return_msg = exp_info
            self.log(exp_info)
            return self.last_return_msg
        return cmdclient

    def make_socks5_tunnel(self, bind_ip="127.0.0.1"):
        """
        建立正向SSH隧道
        建立SockS5隧道
        """
        proxy_list = self.login.get("hostProxyList", [])
        proxy_num = len(proxy_list)
        for i in range(proxy_num):
            # 获取代理端口池
            proxy_pg = self.get_proxy_port_group()
            lockfile = proxy_pg["lockfile"]
            start_port, end_port = proxy_pg['pool']
            # 创建文件锁, 避免建立SSH隧道时端口重用问题
            fp = open(lockfile, "a+", encoding="utf-8")
            # 给文件加锁, 并且这里如果检查到已加锁, 进程会被阻塞等待
            flock(fp.fileno(), LOCK_EX)
            proxy_info = copy(proxy_list[i])
            bind_port = self.get_available_port(start_port, end_port)
            fp.write(str(bind_port) + ",")
            if i == proxy_num - 1:
                # 最后一个proxy主机, 建立SockS5隧道
                host_ip = self.login['ip']
                host_port = self.login['port']
                self.login['hostProxyIp'] = bind_ip
                self.login['hostProxyPort'] = bind_port
                tunnel_type = "dynamic"
                ssh_tunnel = ":".join([bind_ip, str(bind_port)])
                # 设置SockS5代理
                self.login["socks5Proxy"] = {
                    "ip": bind_ip,
                    "port": bind_port
                }
                # socks.set_default_proxy(socks.SOCKS5, bind_ip, int(bind_port))
                # socket.socket = socks.socksocket

            else:
                # 最后一个之前的proxy主机, 建立正向SSH隧道
                host_ip = proxy_list[i + 1]['ip']
                host_port = proxy_list[i + 1]['port']
                tunnel_type = "local"
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
            cmdclient = self.create_ssh_tunnel(tunnel_type, ssh_tunnel, proxy_info)
            self.proxy_ssh_tunnels.append({
                "ssh_tunnel": ssh_tunnel,
                "bind_ip": bind_ip,
                "bind_port": bind_port,
                "proxy_info": proxy_info,
                "cmdclient": cmdclient
            })
            # 使文件锁失效
            fp.close()

    def set_socks5_proxy(self):
        """
        Set up the socks5 proxy
        """
        socks5_proxy = self.login['socks5Proxy']
        ss5_ip = socks5_proxy['ip']
        ss5_port = socks5_proxy['port']
        ss5_user = socks5_proxy.get('username')
        ss5_pswd = socks5_proxy.get('password')
        socks.set_default_proxy(socks.SOCKS5, ss5_ip, int(ss5_port), True, ss5_user, ss5_pswd)
        socket.socket = socks.socksocket
        self.log("Set up the socks5 proxy: %s:%s" % (ss5_ip, ss5_port))

    def connect(self, transport='ntlm', login=None, idx=0):
        """
        连接远程Windows主机
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
                self.make_socks5_tunnel()
            if self.login.get("socks5Proxy"):
                self.set_socks5_proxy()
            ret = self._connect(transport=transport)
        return ret

    def close(self):
        """
        关闭连接
        """
        try:
            self.close_shell()
        except Exception as e:
            raise Exception(f"Failed to colse db connection, exception: {e}") from e
        # 关闭ssh隧道终端
        try:
            for proxy_ssh_tunnel in self.proxy_ssh_tunnels:
                proxy_ssh_tunnel['cmdclient'].close()
        except Exception as e:
            self.log("SSH close tunnel tty exception: %s" % str(e))

    def runcmd(self, cmdstr, args=()):
        """
        Run a command using cmd
        """
        self.reset_result(runcmd=True, rundict=True)
        if not self.shell_id:
            self.open_shell()
        self.log('Run command line: [%s], length: %s, shell_id: %s' % (cmdstr, len(cmdstr), self.shell_id))
        command_id = self.protocol.run_command(self.shell_id, cmdstr, args)
        rs = Response(self.protocol.get_command_output(self.shell_id, command_id))
        self.protocol.cleanup_command(self.shell_id, command_id)
        self.last_return_msg = rs.std_out.decode(encoding=self.encoding, errors='ignore')
        self.cmd_result['runcmd'] = [line.strip() for line in self.last_return_msg.strip().split(self.env.win_linesep)]
        self.last_error_msg = rs.std_err.decode(encoding=self.encoding, errors='ignore')
        self.last_return_code = rs.status_code
        return rs

    def runpowershell(self, script, cmdenv=()):
        """
        Run a command using powershell
        base64 encodes a Powershell script and executes the powershell
        encoded script command
        """
        cmd_cmd = ""
        for cmd in cmdenv:
            if cmd:
                cmd_cmd = cmd_cmd + cmd + " && "
        # must use utf16 little endian on windows
        encoded_ps = b64encode(script.encode('utf_16_le')).decode('ascii')
        ps_cmd = 'powershell -encodedcommand {0}'.format(encoded_ps)
        rs = self.runcmd("%s %s" % (cmd_cmd, ps_cmd))
        if len(rs.std_err):
            # if there was an error message, clean it it up and make it human readable
            rs.std_err = self._clean_error_msg(rs.std_err)
        return rs

    def rundict(self, cmd_dict, args=()):
        """
        使用 CMD 执行多行命令
        注意：仅支持多行配合使用的交互式命令:
              1)发送最后一行命令之前不能回到终端默认提示符，否则会发送失败;
              2)最后一行命令执行后也不能回到终端默认提示符，否则获取不到中间命令回显内容.
        """
        self.reset_result(runcmd=True, rundict=True)
        if cmd_dict:
            if not self.shell_id:
                self.open_shell()
            command_id = None
            idx = 0
            cmd_num = len(cmd_dict)
            for cmdname in cmd_dict:
                idx = idx + 1
                cmdstr = str(cmd_dict[cmdname]).strip()
                self.log('Run command line: [%s], length: %s, shell_id: %s' % (cmdstr, len(cmdstr), self.shell_id))
                if not command_id:
                    command_id = self.protocol.run_command(self.shell_id, cmdstr, args)
                else:
                    if idx == cmd_num:
                        self.protocol.send_command_input(self.shell_id, command_id, cmdstr.encode(), end=True)
                    else:
                        self.protocol.send_command_input(self.shell_id, command_id, cmdstr.encode(), end=False)
            # self.protocol.send_command_input(self.shell_id, command_id, "\t\n", end=True)
            rs = Response(self.protocol.get_command_output(self.shell_id, command_id))
            self.protocol.cleanup_command(self.shell_id, command_id)
            self.last_return_msg = rs.std_out.decode(encoding=self.encoding, errors='ignore')
            self.cmd_result['runcmd'] = self.last_return_msg.strip().split(self.env.win_linesep)
            self.last_error_msg = rs.std_err.decode(encoding=self.encoding, errors='ignore')
            self.last_return_code = rs.status_code
        else:
            rs = Response(("No command was executed", "", "0"))
        return rs

# vi:ts=4:sw=4:expandtab:ft=python:
