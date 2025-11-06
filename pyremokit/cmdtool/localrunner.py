#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
本地命令执行工具类库: 通过封装subprocess实现本地执行命令并获取执行结果
'''

import getpass
import os
# import pty
import re
import subprocess
import sys
import threading
import time

from collections import OrderedDict

from pyremokit.baserunner import BaseRunner
from pyremokit.cmdtool.localenv import LocalEnv


__all__ = ['LocalEnv', 'LocalRunner']


class LocalRunner(BaseRunner):

    def __init__(self, envpointer=None, timeout=30):
        """
        本地执行工具类
        """
        super().__init__(envpointer)
        self.timeout = timeout

        self.codedset = ['utf-8', 'gb18030']
        self.stop_flag = "stop"
        self.define_error_msg = "error-chkthread-exit"
        self.define_output_msg = "interactive-mode-exit"

        if sys.platform in ('win32', 'cygwin'):
            self.crlf = '\r\n'
            self.subproc = 'cmd'
            self.make_error_msg = '@echo "%s"' % self.define_error_msg
            self.make_output_msg = '@echo "%s"' % self.define_output_msg
        else:
            self.crlf = '\n'
            self.subproc = 'bash'
            self.make_error_msg = 'echo "%s"' % self.define_error_msg
            self.make_output_msg = 'echo "%s"' % self.define_output_msg

        self.readingnohup = False
        self.errchecking = False
        self.__checkerr = False
        self.tty_sendkey = {}
        self.tty_receive = {}
        self.tty = {}
        self.tty['login'] = self.make_subprocess_popen()
        # self.tty['suuser'] = self.make_subprocess_popen(args=pty.spawn("/bin/bash"))
        self.tty['suuser'] = self.make_subprocess_popen()

    def make_subprocess_popen(self, args=None, shell=True):
        """
        使用Popen创建TTY进程
        """
        try:
            if not args:
                args = self.subproc
            _process = subprocess.Popen(args,
                                        shell=shell,
                                        stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE
                                        )
            if _process.stdin.closed:
                raise Exception('TTY已被关闭')
        except Exception as ex:
            raise Exception('创建TTY进程失败: %s' % str(ex)) from ex
        return _process

    def close(self, _process):
        """
        关闭TTY进程
        """
        try:
            # 防止连接已被意外关闭
            pid = _process.pid
            if not _process.stdout.closed:
                _process.stdout.close()
            if not _process.stdin.closed:
                _process.stdin.close()
            if not _process.stderr.closed:
                _process.stderr.close()
            _process.terminate()
        except Exception as ex:
            self.log("WARN: close tty session exception: %s" % str(ex))
        self.log("The TTY %s session is closed." % pid)

    def close_all(self):
        """
        关闭所有TTY进程
        """
        # self.close(self.tty['login'])
        # self.close(self.tty['suuser'])
        for name, _process in self.tty.items():
            self.log("Close the TTY(%s) session." % name)
            self.close(_process)

    def runcmd(self, cmdstr, ttyhandle=None):
        """
        运行单个命令
        在指定的TTY环境下执行命令，ttyhandle为None表示在当前登录用户的shell环境，其他值(必须是suuser返回的)表示在切换后的用户shell下执行
        支持上下文关系
        命令全部写入stdin后一次性提交，语句间的上下文关系成立，执行完成后会话断开，TTY被关闭不可用
        适用于不关注每条具体命令回显、管道场景
        成功返回0，非0为错误代码，命令回显保存在LocalRunner.cmd_result['runcmd']中，或使用get_lastmsg返回一个字符串
        这两个函数不关注是否有回显，只要是合法命令都能提交执行，返回一个所有命令的执行结果的字符串，保存在last_return_msg
        但是务必注意，这两个函数无论哪一个，一旦执行，则该实例无法再继续执行任何场景任务或命令
        """
        self.check_param('cmdstr', cmdstr,
                         genreplyfile=True,
                         currentfile=__file__,
                         currentfun=sys._getframe().f_code.co_name,
                         currentline=sys._getframe().f_lineno
                         )
        self.reset_result(runcmd=True)
        try:
            _process = self.make_subprocess_popen(shell=True)
            self.log('Run local cmd: [' + cmdstr + ']')
            cmdstr_b = bytes(cmdstr + self.crlf, encoding='utf-8')
            _process.stdin.write(cmdstr_b)
            _process.stdin.flush()
            # 提交，等待子进程结束
            outmsg, errmsg = _process.communicate()
            self.last_return_code = _process.returncode
            if isinstance(outmsg, bytes):
                outmsg = outmsg.decode(encoding="utf-8")
            if isinstance(errmsg, bytes):
                outmsg = outmsg.decode(encoding="utf-8")
                errmsg = errmsg.decode(encoding="utf-8")
            self.last_return_msg = outmsg

            if errmsg:
                self.last_return_msg += errmsg
                self.log(self.last_return_msg)

            self.cmd_result['runcmd'] = self.last_return_msg.splitlines(False)
            # self.log('Return msg: [\n' + self.last_return_msg + '\n]')
            self.log('Return msg: %s' % self.cmd_result['runcmd'])
            self.close(_process)
        except Exception as ex:
            exp_info = '打开进程执行命令发生异常: ' + str(ex)
            self.last_return_msg = exp_info
            self.cmd_result['result'] = exp_info.splitlines(False)
            if not self.last_return_code:
                self.last_return_code = -1

        return self.last_return_code

    def rundict(self, cmd_dict, onebyone=False):
        """
        运行多个命令
        """
        self.check_param('cmd_dict', cmd_dict,
                         genreplyfile=True,
                         currentfile=__file__,
                         currentfun=sys._getframe().f_code.co_name,
                         currentline=sys._getframe().f_lineno
                         )
        self.reset_result(rundict=True)
        try:
            if onebyone:
                # 逐条
                for cmdname in cmd_dict:
                    cmd = cmd_dict[cmdname]
                    self.runcmd(cmd)
                    # 如果有失败的执行记录，则退出不继续执行剩余
                    if self.get_lastcode() == 0:
                        # self.cmd_result[cmdname] = self.get_lastmsg()
                        self.cmd_result[cmdname] = self.cmd_result['runcmd']
                    else:
                        break
            else:
                # 批量
                _process = self.make_subprocess_popen(shell=True)
                for cmdname in cmd_dict:
                    cmd = cmd_dict[cmdname]
                    self.log('Run local cmd: [' + cmd + ']')
                    # self.log('Run remote cmd length: ' + str(len(cmd)))
                    cmdstr_b = bytes(cmd + self.crlf, encoding='utf-8')
                    _process.stdin.write(cmdstr_b)
                    _process.stdin.flush()
                # 提交，等待子进程结束
                outmsg, errmsg = _process.communicate()
                self.last_return_code = _process.returncode
                if isinstance(outmsg, bytes):
                    outmsg = outmsg.decode(encoding="utf-8")
                if isinstance(errmsg, bytes):
                    errmsg = errmsg.decode(encoding="utf-8")
                self.last_return_msg = outmsg
                if errmsg:
                    self.last_return_msg += errmsg
                    self.log(self.last_return_msg)

                self.cmd_result['runcmd'] = self.last_return_msg.splitlines(False)
                # self.log('Return msg: [\n' + self.last_return_msg + '\n]')
                self.log('Return msg: %s' % self.cmd_result['runcmd'])
                self.close(_process)
        except Exception as ex:
            exp_info = '打开进程执行命令发生异常: ' + str(ex)
            self.last_return_msg = exp_info
            self.cmd_result['result'] = exp_info.splitlines(False)
            if not self.last_return_code:
                self.last_return_code = -1

        return self.last_return_code

    def run_inos(self, param_list, cmd_list):
        """
        直接在OS中运行指定的程序并与之交互数据
        param_list：列表，指定要执行的程序及传递给该程序的参数
        cmd_list：列表，指定的程序运行到内存之后二次交互给该进程的指令，
                例如运行sqlplus之后在sqlplus中执行的命令，例如su用户的密码提交和后续命令
        成功返回0，非0为错误代码，命令回显保存在LocalRunner.cmd_result['runcmd']中，或使用get_lastmsg返回一个字符串

        """
        self.check_param('param_list', param_list,
                         genreplyfile=True,
                         currentfile=__file__,
                         currentfun=sys._getframe().f_code.co_name,
                         currentline=sys._getframe().f_lineno
                         )
        self.reset_result(runcmd=True)
        try:
            # shell必须为False
            _process = self.make_subprocess_popen(shell=False)
            if cmd_list is not None and len(cmd_list):
                for cmd in cmd_list:
                    self.log('Run local raw cmd: [' + cmd + ']')
                    cmdstr_b = bytes(cmd + self.crlf, encoding='utf-8')
                    _process.stdin.write(cmdstr_b)
                    _process.stdin.flush()

            # 提交，等待子进程结束
            outmsg, errmsg = _process.communicate()
            self.last_return_code = _process.returncode
            if isinstance(outmsg, bytes):
                outmsg = outmsg.decode(encoding="utf-8")
            if isinstance(errmsg, bytes):
                errmsg = errmsg.decode(encoding="utf-8")
            self.last_return_msg = outmsg
            if errmsg:
                self.last_return_msg += errmsg
                self.log(self.last_return_msg)

            self.cmd_result['runcmd'] = self.last_return_msg.splitlines(False)
            self.log(self.last_return_msg)
            self.close(_process)

        except Exception as ex:
            exp_info = '打开进程执行命令发生异常: ' + str(ex)
            self.last_return_msg = exp_info
            self.cmd_result['result'] = exp_info.splitlines(False)
            if not self.last_return_code:
                self.last_return_code = -1

        return self.last_return_code

    def __bytes_to_str(self, _b):
        """
        bytes -> str
        """
        _s = ""
        try:
            if isinstance(_b, bytes):
                # _s = _b.decode(self.codedset[0])
                _s = str(_b, encoding=self.codedset[0])
            else:
                _s = str(_b)
        except UnicodeDecodeError:
            _s = _b.decode(self.codedset[1])
        except Exception as ex:
            _s = _b
            self.log('Format conversion exception: %s' % ex)
        return _s

    def __str_to_bytes(self, _s):
        """
        str -> bytes
        """
        _b = b""
        try:
            if isinstance(_s, str):
                _b = bytes(_s, encoding='utf-8')
                # _b = _s.encode('utf-8')
            else:
                _b = _s
        except Exception as ex:
            _b = _s
            self.log('Format conversion exception: %s' % ex)
        return _b

    def __timeout(self, ttyname, wait_time=1):
        """
        是否产生结果记录，并作读取超时判断
        """
        timeout = 0
        readlines = 0
        secondreadlines = 0
        while not readlines:
            if timeout >= self.timeout:
                return True
            timeout += 0.1
            time.sleep(0.1)
            readlines = int(self.tty_receive.get(ttyname, 0))

        # 等待100毫秒以完成持续的输出,如果连续输出间隔超过100毫秒将被视为输出已完成
        # 持续输出超过1分钟之后的内容将被丢弃，但是有可能被当成本次会话中下一条命令的回显,产生干扰
        timeout = 0
        while readlines != secondreadlines:
            if timeout >= self.timeout:
                return True
            readlines = int(self.tty_receive.get(ttyname, 0))
            # timeout += 0.1
            # time.sleep(0.1)
            timeout += wait_time
            time.sleep(wait_time)
            secondreadlines = int(self.tty_receive.get(ttyname, 0))
        return False

    def __check_stderr(self, ttyname, _process):
        """
        线程函数，检查stderr是否有输出
        """
        self.log('持久会话_错误检测线程: 启动')
        readlines = 0
        key = ''
        self.errchecking = True
        try:
            while True:
                if _process.stderr.closed:
                    break
                # 正常情况下这里读取stderr信息会被阻塞住
                _errline = _process.stderr.readline()
                errline = self.__bytes_to_str(_errline)
                # 获取执行的命令信息
                sendkey = self.tty_sendkey.get(ttyname)
                if sendkey and key != sendkey:
                    readlines = 0
                    key = sendkey
                if key == self.stop_flag:
                    break
                # 处理stderr信息
                if errline:
                    self.log('Stderr line: %s' % errline)
                    minestr = str(errline)
                    if minestr.find(self.define_output_msg) != -1 or minestr.find(self.define_error_msg) != -1:
                        continue
                    self.last_return_code = -1
                    sendkey = self.tty_sendkey.get(ttyname)
                    if sendkey:
                        key = sendkey
                    if not self.cmd_result.get(key):
                        self.cmd_result[key] = []
                    # 记录命令结果
                    self.last_return_msg += errline
                    self.cmd_result[key].append(self.last_return_msg)
                    readlines += 1
                    self.tty_receive[ttyname] = readlines
                    self.__checkerr = True
                else:
                    self.log('Stderr readline null!')
                    # break
        except IOError:
            # stdout IO 读取错误
            self.last_return_code = -100
            self.last_return_msg = 'stderr IO 读取错误!'
            readlines += 1
            self.tty_receive[ttyname] = readlines
            self.log(self.last_return_msg)

        self.errchecking = False
        self.log('持久会话_错误检测线程: 退出!')
        return self.last_return_code

    def __rcvin_thread(self, ttyname, _process):
        """
        外部用两个相差100毫秒的self.tty_receive[ttyname]来判断当前接收线程是否已经被阻塞了
        内部用self.tty_sendkey[ttyname]="stop"来告诉当前线程是否退出
        """
        self.log('持久会话_回显接收线程: 启动!')
        readlines = 0
        key = ''
        self.last_return_msg = ''
        try:
            while True:
                # 先不着急读stdout，因为一旦指令执行出错时输出结果在stderr，这时stdout.readline会被阻塞
                if self.__checkerr:
                    break
                if _process.stdout.closed:
                    break
                # readlin在读空缓冲区后将会阻塞,当从阻塞状态下恢复时将从这里开始继续执行
                _outline = _process.stdout.readline()
                outline = self.__bytes_to_str(_outline)
                if self.__checkerr:   # 切换场景出错时，错误与正常输出可能同时存在
                    break

                sendkey = self.tty_sendkey.get(ttyname)
                if sendkey:
                    if key != sendkey:
                        readlines = 0
                        key = sendkey
                else:
                    time.sleep(0.1)
                    continue
                if key == self.stop_flag:
                    self.log('丢弃的残余消息: ' + outline)
                    break

                if outline:
                    self.log('Stdout line: %s' % outline)
                    minestr = str(outline)
                    if minestr.find(self.define_output_msg) != -1 or minestr.find(self.define_error_msg) != -1:
                        continue
                    if not self.cmd_result.get(key):
                        self.last_return_msg = ''
                        self.cmd_result[key] = []
                    self.last_return_msg += outline
                    self.cmd_result[key].append(outline)
                    readlines += 1
                    self.tty_receive[ttyname] = readlines
                else:
                    # # 回显已读完，这是最理想的非阻塞的情况
                    # readlines += 1
                    # self.tty_receive[ttyname] = readlines
                    # break
                    self.log('Stdout readline null!')
        except IOError:
            # stdout IO 读取错误
            self.last_return_code = -100
            self.last_return_msg = 'Stdout IO 读取错误!'
            readlines += 1
            self.tty_receive[ttyname] = readlines
            self.log(self.last_return_msg)

        self.log('持久会话_回显接收线程: 退出!')
        return self.last_return_code

    def __do_command(self, ttyname, cmd_dict, wait_time):
        """
        执行命令
        在指定的TTY环境下执行命令
         - ttyname为login表示在当前登录用户的shell环境
         - ttyname为suuser表示在切换后的用户shell下执行
        支持上下文关系
        持续会话,命令逐行"提交并等待回显"，执行完毕后继续监听shell的stdout
        只要未手动关闭会话，可连续调用此函数，后续执行的命令可保持之前语句的上下文环境
        注意：每行执行的命令必须要有回显!否则会走超时报错并且进程无法结束
        例如cd到某个目录应该这样写：'cd /home;pwd'，借助pwd的回显结束本行语句
        """
        # TTY会话
        _process = self.tty[ttyname]
        # 将上一次调用的环境初始化
        self.tty_sendkey[ttyname] = ''
        self.__checkerr = False
        # 启动接受信息线程
        rcvthread = threading.Thread(target=self.__rcvin_thread, args=(ttyname, _process))
        rcvthread.start()
        if not rcvthread.is_alive():
            # stdout IO 读取错误
            self.last_return_code = -100
            self.last_return_msg = '创建接收信息线程失败!'
            self.log(self.last_return_msg)
            return self.last_return_code

        if _process.stdin.closed:
            # stdin IO 读取错误
            self.last_return_code = -100
            self.last_return_msg = 'stdin 被关闭!'
            self.log(self.last_return_msg)
            return self.last_return_code

        # 清空数据接收区
        self.reset_result(runcmd=True, rundict=True)

        for key, value in cmd_dict.items():
            self.tty_receive[ttyname] = 0
            # 更新本次命令key
            self.tty_sendkey[ttyname] = key
            self.log('Run local cmd: [' + value + ']')
            _process.stdin.write(self.__str_to_bytes(value + self.crlf))
            _process.stdin.flush()

            # 结果是否可读，并作超时判断
            if self.__timeout(ttyname, wait_time):
                # stdout IO 读取超时错误
                self.last_return_code = -200
                self.last_return_msg = '执行命令超时: [' + value + ']'
                self.log(self.last_return_msg)
                break

            self.log("Result: " + self.last_return_msg)

            # __check_stderr 线程检查到错误信息
            if self.__checkerr:
                break

        # 设置一个停止标志让__rcvin_thread 和 __check_stderr 检查线程退出
        self.tty_sendkey[ttyname] = self.stop_flag
        self.log("Set stop flag: " + self.stop_flag)

        # 发送一个无意义但是有回显的命令让接收线程退出
        _process.stdin.write(self.__str_to_bytes(self.make_output_msg + self.crlf))
        _process.stdin.flush()
        time.sleep(1)

        return self.last_return_code

    def runcmd_interactive(self, cmdstr, ttyhandle=None, wait_time=1):
        """
        在指定的TTY环境下执行单个命令
        """
        self.check_param('cmdstr', cmdstr,
                         genreplyfile=True,
                         currentfile=__file__,
                         currentfun=sys._getframe().f_code.co_name,
                         currentline=sys._getframe().f_lineno
                         )
        cmd_dict = {'runcmd': cmdstr}
        return self.rundict_interactive(cmd_dict, ttyhandle, wait_time)

    def rundict_interactive(self, cmd_dict, ttyhandle=None, wait_time=1):
        """
        在login用户下执行，ttyhandle为None，否则先执行suuser得到一个tty
        """
        self.check_param('cmd_dict', cmd_dict,
                         genreplyfile=True,
                         currentfile=__file__,
                         currentfun=sys._getframe().f_code.co_name,
                         currentline=sys._getframe().f_lineno
                         )
        res = None
        if ttyhandle and self.tty['suuser'] == ttyhandle:
            res = self.__do_command('suuser', cmd_dict, wait_time)
        else:
            res = self.__do_command('login', cmd_dict, wait_time)
        return res

    def suuser(self, username, passwd):
        """
        切换用户，获取tty会话
        """
        _process = self.tty['suuser']
        self.check_param('username', username,
                         genreplyfile=True,
                         currentfile=__file__,
                         currentfun=sys._getframe().f_code.co_name,
                         currentline=sys._getframe().f_lineno
                         )
        # getpass.getuser() 能准确取到当前执行此脚本的用户名
        userbeforesu = getpass.getuser()
        if userbeforesu == username:
            self.log('当前用户 %s 与su切换用户相同!' % username)
            # return _process

        if userbeforesu != 'root':
            self.check_param('password', passwd,
                             genreplyfile=True,
                             currentfile=__file__,
                             currentfun=sys._getframe().f_code.co_name,
                             currentline=sys._getframe().f_lineno
                             )
        su_cmd = 'su - ' + username
        self.log('Run local cmd: [' + su_cmd + ']')
        self.reset_result()
        if _process.stdin.closed:
            # stdin IO 读取错误
            self.last_return_code = -100
            self.last_return_msg = 'stdin 被关闭!'
            return None

        _process.stdin.write(self.__str_to_bytes(su_cmd + self.crlf))
        _process.stdin.flush()
        if userbeforesu != 'root':
            _process.stdin.write(self.__str_to_bytes(passwd + self.crlf))
            _process.stdin.flush()

        res = self.runcmd_interactive('whoami', _process)
        if not res:
            self.log('切换至用户 %s 成功: %s' % (username, self.get_lastmsg()))
            return _process

    def readinglogfile(self, filename, lastline_num, func_callback, endflag="##SCRIPT##EXEC##END##"):
        """
        创建线程持续读日志文件
        """
        self.readingnohup = True
        paramtuple = (filename, lastline_num, func_callback, endflag)
        tailthread = threading.Thread(target=self.tailf, args=paramtuple)
        tailthread.start()
        if not tailthread.is_alive():
            rtnflag = False
            rtnmsg = '创建 tailf 线程失败'
        else:
            rtnflag = True
            rtnmsg = '创建 tailf 线程成功'
        return rtnflag, rtnmsg

    def stopreadinglogfile(self):
        self.readingnohup = False
        time.sleep(0.5)

    def tailf(self, filename, lastline_num, func_callback, endflag):
        """
        读取最后 lastline_num 行数的内容
        """
        if not os.path.exists(filename):
            tail_file = open(filename, 'a+', encoding='utf-8')
            tail_file.close()
            os.chmod(filename, 0o777)
        try:
            self.log("Start read local file: %s" % filename)
            tail_file = open(filename, 'r', encoding='utf-8')
            tail_file.seek(0, 2)
            # 文件的字符长度
            file_length = tail_file.tell()
            # 打印最后 lastline_num 行
            if lastline_num > 0:
                self.show_last_line(tail_file, file_length, lastline_num, func_callback)
            # 持续读文件 打印增量
            times = 0
            while self.readingnohup:
                line = tail_file.readline()
                if line:
                    # 屏蔽密码显示
                    if re.match(r'.*?\'s password:\.*', line):
                        continue
                    if line.find('[PEXPECT]') != -1:
                        # 当回显内容或返回值与提示符混到同一行拿到时，要处理这种情况
                        if len(line.strip()) == len('[PEXPECT]$'):
                            line = line.replace('[PEXPECT]$', '').strip()
                            line = line.replace('[PEXPECT]#', '').strip()
                            line = line.replace('[PEXPECT]>', '').strip()
                            # line = line.replace('[PEXPECT]', '').strip()
                            if not line:
                                continue
                    if func_callback:
                        func_callback(line)
                    else:
                        self.log(line)
                    # 判断结束标准
                    if line.find(endflag) > -1:
                        break
                    # 超时 24h 退出: 24*3600*5 = 432000
                    if times > 432000:
                        break
                time.sleep(0.2)
                times += 1
            rtnflag = True
            rtnmsg = endflag
        except Exception as ex:
            rtnflag = False
            rtnmsg = str(ex)
        return rtnflag, rtnmsg

    def show_last_line(self, filehandle, filelen, lastline_num, func_callback):
        """
        先读出来最后 line_len * n 个字符（按每行1000字符估算），然后计算换行符取最后n行输出
        """
        line_len = 1000
        read_len = line_len * lastline_num

        while True:
            # 如果要读取的字符长度大于文件长度
            if read_len > filelen:
                # seek(0,0) 默认移动到文件开头或简写成seek(0)
                filehandle.seek(0)
                last_lines = filehandle.read().decode(encoding="utf-8").split('\n')
                break
            # seek(x,2) 表示从文件末尾向后移x（正数）个字节，如果x负数，则是从末尾向前移动x个字节
            filehandle.seek(-read_len, 2)
            last_words = filehandle.read(read_len).decode(encoding="utf-8")
            # count是换行符的数量
            count = last_words.count('\n')
            if count >= lastline_num:
                # 换行符数量大于目标获取行数时，直接读取
                last_lines = last_words.split('\n')[-lastline_num:]
                break
            else:
                # 换行符数量小于目标获取行数时，重设每行长度
                if count == 0:
                    len_perline = read_len
                else:
                    len_perline = int(read_len / count)

                # 重新计算评估读取目标行数的字符数量
                read_len = len_perline * lastline_num

        for line in last_lines:
            if func_callback:
                func_callback(line)
            else:
                self.log(line)


if __name__ == "__main__":

    lenv = LocalEnv(logpath=None, logfile=None, parsescript=False, printtostdout=False)
    lr = LocalRunner(envpointer=lenv)
    print(lr.tty)

    print('-' * 50 + "运行一次单个命令" + '-' * 50)
    ret = lr.runcmd('python -c "import os; print(os.getlogin())"')
    print("exit code: %s" % ret)
    print("return msg: %s" % lr.get_lastmsg())
    print("return list: %s" % lr.get_cmd_return('runcmd'))

    print('-' * 50 + "运行一次多个命令" + '-' * 50)
    cmddict = OrderedDict()
    cmddict['cmd1'] = 'ls -l'
    cmddict['cmd2'] = 'pwd'
    cmddict['cmd3'] = 'hostname'
    cmddict['cmd4'] = 'date'
    cmddict['cmd5'] = 'who'
    cmddict['cmd6'] = 'echo "$PATH"'
    ret = lr.rundict(cmddict)
    print("exit code: %s" % ret)
    print("return msg: %s" % lr.get_lastmsg())
    print("return list: %s" % lr.get_cmd_return('runcmd'))

    print('-' * 50 + "运行指定程序环境的命令" + '-' * 50)
    ret = lr.run_inos(['bash'], ['pwd', 'date'])
    print("exit code: %s" % ret)
    print("return msg: %s" % lr.get_lastmsg())
    print("return list: %s" % lr.get_cmd_return('runcmd'))

    print('-' * 50 + "持续执行多个命令" + '-' * 50)
    cmddict = OrderedDict()
    cmddict['cmd1'] = 'ls -l'
    cmddict['cmd2'] = 'pwd'
    cmddict['cmd3'] = 'hostname'
    cmddict['cmd4'] = 'date'
    cmddict['cmd5'] = 'whoami'
    ret = lr.rundict_interactive(cmddict)
    print("exit code: %s" % ret)
    print("return msg: %s" % lr.get_lastmsg())
    print("return list: %s" % lr.get_cmd_return('runcmd'))

    print('-' * 50 + "持续执行单个命令" + '-' * 50)
    ret = lr.runcmd_interactive('hostname')
    print("exit code: %s" % ret)
    print("return msg: %s" % lr.get_lastmsg())
    print("return list: %s" % lr.get_cmd_return('runcmd'))

    print('-' * 50 + "切换用户" + '-' * 50)
    _process = lr.suuser('test', '123456')
    ret = lr.runcmd_interactive('id', _process)
    print("exit code: %s" % ret)
    print("return msg: %s" % lr.get_lastmsg())
    print("return list: %s" % lr.get_cmd_return('runcmd'))
    ret = lr.runcmd_interactive('pwd', _process)
    print("exit code: %s" % ret)
    print("return msg: %s" % lr.get_lastmsg())
    print("return list: %s" % lr.get_cmd_return('runcmd'))
    lr.close(_process)

    print('-' * 50 + "关闭所有TTY进程" + '-' * 50)
    lr.close_all()

    print('-' * 50 + "tailf方式读文件" + '-' * 50)
    filename = '/var/log/cmp/emc/script_2022-11-21.log'
    # stat, msg = lr.readinglogfile(filename, 10, None)
    stat, msg = lr.readinglogfile(filename, 10, print)
    # stat, msg = lr.tailf(filename, 10, print)
    print(stat, msg)
    time.sleep(5)
    lr.stopreadinglogfile()

# vi:ts=4:sw=4:expandtab:ft=python:
