#!/usr/bin/env python
# -*- coding: utf-8 -*-

'''
继承 pexpect.pxssh 扩展方法
'''

import sys
import os
import re
from pexpect import EOF
from pexpect import TIMEOUT
from pexpect import spawn
from pexpect.pxssh import pxssh
from pexpect.pxssh import ExceptionPxssh


if sys.version_info > (3, 0):
    from shlex import quote
else:
    _find_unsafe = re.compile(r'[^\w@%+=:,./-]').search

    def quote(s):
        """Return a shell-escaped version of the string *s*."""
        if not s:
            return "''"
        if _find_unsafe(s) is None:
            return s

        # use single quotes, and put single quotes into double quotes
        # the string $'b is then quoted as '$'"'"'b'
        return "'" + s.replace("'", "'\"'\"'") + "'"


class PEXPSSH(pxssh):
    """
    扩展pxssh类:
    1) 增加修改密码方法
    2) 登录登出Lpar控制台
    3) 设置系统字符集（临时生效）
    """

    def __init__(self, timeout=30, maxread=2000, searchwindowsize=None,
                logfile=None, cwd=None, env=None, ignore_sighup=True,
                echo=True, options={}, encoding=None, codec_errors='strict',
                debug_command_string=False, use_poll=False):

        super(PEXPSSH, self).__init__(timeout=timeout,
                                      maxread=maxread,
                                      searchwindowsize=searchwindowsize,
                                      logfile=logfile,
                                      cwd=cwd,
                                      env=env,
                                      ignore_sighup=ignore_sighup,
                                      echo=echo,
                                      options=options,
                                      encoding=encoding,
                                      codec_errors=codec_errors,
                                      debug_command_string=debug_command_string,
                                      use_poll=use_poll)

    def first_login_change_passwd(self, server, port=None, username=None,
                                  password='', new_password='',
                                  ssh_key=None, quiet=True,
                                  login_timeout=10, terminal_type='ansi',
                                  original_prompt=r"[#$>]", auto_prompt_reset=True,
                                  sync_multiplier=1, check_local_ip=True,
                                  password_regex=r'(?i)(?:password:)|(?:passphrase for key)',
                                  ssh_tunnels={}, spawn_local_ssh=True,
                                  sync_original_prompt=True, ssh_config=None, cmd='ssh'):
        """
        登录并修改密码方法
        """

        session_regex_array = [
            "(?i)are you sure you want to continue connecting",
            original_prompt,
            r"^(?:.*s Old password:)|(?:\(current\) UNIX password:)",
            r"(Enter the new password again:)|(?:Retype new password: )",
            ".*New password: ",
            password_regex,
            "(?i)permission denied",
            "(?i)terminal type",
            TIMEOUT
        ]
        session_init_regex_array = []
        session_init_regex_array.extend(session_regex_array)
        session_init_regex_array.extend(
            ["(?i)connection closed by remote host", EOF])

        ssh_options = ''.join([" -o '%s=%s'" % (o, v)
                              for (o, v) in self.options.items()])
        if quiet:
            ssh_options = ssh_options + ' -q'
        if not check_local_ip:
            ssh_options = ssh_options + " -o'NoHostAuthenticationForLocalhost=yes'"
        if self.force_password:
            ssh_options = ssh_options + ' ' + self.SSH_OPTS
        if ssh_config is not None:
            if spawn_local_ssh and not os.path.isfile(ssh_config):
                raise ExceptionPxssh(
                    'SSH config does not exist or is not a file.')
            ssh_options = ssh_options + ' -F ' + ssh_config
        if port is not None:
            ssh_options = ssh_options + ' -p %s' % (str(port))
        if ssh_key is not None:
            # Allow forwarding our SSH key to the current session
            if ssh_key == True:
                ssh_options = ssh_options + ' -A'
            else:
                if spawn_local_ssh and not os.path.isfile(ssh_key):
                    raise ExceptionPxssh(
                        'private ssh key does not exist or is not a file.')
                ssh_options = ssh_options + ' -i %s' % (ssh_key)

        # SSH tunnels, make sure you know what you're putting into the lists
        # under each heading. Do not expect these to open 100% of the time,
        # The port you're requesting might be bound.
        #
        # The structure should be like this:
        # { 'local': ['2424:localhost:22'],  # Local SSH tunnels
        # 'remote': ['2525:localhost:22'],   # Remote SSH tunnels
        # 'dynamic': [8888] } # Dynamic/SOCKS tunnels
        if ssh_tunnels != {} and isinstance({}, type(ssh_tunnels)):
            tunnel_types = {
                'local': 'L',
                'remote': 'R',
                'dynamic': 'D'
            }
            for tunnel_type in tunnel_types:
                cmd_type = tunnel_types[tunnel_type]
                if tunnel_type in ssh_tunnels:
                    tunnels = ssh_tunnels[tunnel_type]
                    for tunnel in tunnels:
                        if spawn_local_ssh == False:
                            tunnel = quote(str(tunnel))
                        ssh_options = ssh_options + ' -' + \
                            cmd_type + ' ' + str(tunnel)

        if username is not None:
            ssh_options = ssh_options + ' -l ' + username
        elif ssh_config is None:
            raise TypeError('login() needs either a username or an ssh_config')
        else:  # make sure ssh_config has an entry for the server with a username
            with open(ssh_config, 'rt') as f:
                lines = [l.strip() for l in f.readlines()]

            server_regex = r'^Host\s+%s\s*$' % server
            user_regex = r'^User\s+\w+\s*$'
            config_has_server = False
            server_has_username = False
            for line in lines:
                if not config_has_server and re.match(server_regex, line, re.IGNORECASE):
                    config_has_server = True
                elif config_has_server and 'hostname' in line.lower():
                    pass
                elif config_has_server and 'host' in line.lower():
                    server_has_username = False  # insurance
                    break  # we have left the relevant section
                elif config_has_server and re.match(user_regex, line, re.IGNORECASE):
                    server_has_username = True
                    break

            if lines:
                del line

            del lines

            if not config_has_server:
                raise TypeError(
                    'login() ssh_config has no Host entry for %s' % server)
            elif not server_has_username:
                raise TypeError(
                    'login() ssh_config has no user entry for %s' % server)

        cmd += " %s %s" % (ssh_options, server)
        if self.debug_command_string:
            return(cmd)

        # Are we asking for a local ssh command or to spawn one in another session?
        if spawn_local_ssh:
            spawn._spawn(self, cmd)
        else:
            self.sendline(cmd)

        # This does not distinguish between a remote server 'password' prompt
        # and a local ssh 'passphrase' prompt (for unlocking a private key).
        i = self.expect(session_init_regex_array, timeout=login_timeout)

        # First phase
        if i == 0:
            # New certificate -- always accept it.
            # This is what you get if SSH does not have the remote host's
            # public key stored in the 'known_hosts' cache.
            self.sendline("yes")
            i = self.expect(session_regex_array)
        if i == 5:  # password or passphrase
            self.sendline(password)
            i = self.expect(session_regex_array)
        if new_password:
            if i == 1:  # 进入系统,未提示修改密码
                self.sendline("passwd")
                i = self.expect(session_regex_array)
            if i == 2:
                self.sendline(password)
                i = self.expect(session_regex_array)
            if i == 4:
                self.sendline(new_password)
                i = self.expect(session_regex_array)
            if i == 3:
                self.sendline(new_password)
                i = self.expect(session_init_regex_array)
            if i == 1:  # 执行passwd修改密码后需要exit退出登录
                self.sendline("exit")
                return True
        if i == 7:
            self.sendline(terminal_type)
            i = self.expect(session_regex_array)
        if i == 9:
            self.close()
            raise ExceptionPxssh('Could not establish connection to host')
        if i == 10:
            self.close()
            # 密码修改成功
            return True

        # Second phase
        if i == 0:
            # This is weird. This should not happen twice in a row.
            self.close()
            raise ExceptionPxssh('Weird error. Got "are you sure" prompt twice.')
        elif i == 1:  # can occur if you have a public key pair set to authenticate.
            ### TODO: May NOT be OK if expect() got tricked and matched a false prompt.
            pass
        elif i == 2 or i == 3 or i == 4:  # You must change your password now and login again!
            self.close()
            raise ExceptionPxssh('bad password')
        elif i == 5:  # password prompt again
            # For incorrect passwords, some ssh servers will
            # ask for the password again, others return 'denied' right away.
            # If we get the password prompt again then this means
            # we didn't get the password right the first time.
            self.close()
            raise ExceptionPxssh('password refused')
        elif i == 6:  # permission denied -- password was bad.
            self.close()
            raise ExceptionPxssh('permission denied')
        elif i == 7:  # terminal type again? WTF?
            self.close()
            raise ExceptionPxssh(
                'Weird error. Got "terminal type" prompt twice.')
        elif i == 8:  # Timeout
            #This is tricky... I presume that we are at the command-line prompt.
            #It may be that the shell prompt was so weird that we couldn't match
            #it. Or it may be that we couldn't log in for some other reason. I
            #can't be sure, but it's safe to guess that we did login because if
            #I presume wrong and we are not logged in then this should be caught
            #later when I try to set the shell prompt.
            pass
        elif i == 9:  # Connection closed by remote host
            self.close()
            raise ExceptionPxssh('connection closed')
        else:  # Unexpected
            self.close()
            raise ExceptionPxssh('unexpected login response')
        if sync_original_prompt:
            if not self.sync_original_prompt(sync_multiplier):
                self.close()
                raise ExceptionPxssh(
                    'could not synchronize with original prompt')
        return True

    def login_console(self, managed_host, lpar_name, user, password, login_timeout=10):
        """
        登录Lpar控制台
        """
        session_regex_array = [
            self.PROMPT,
            r"[$#>]",
            r"(?i)Console login:",
            # r"Console login:",
            r"(?i).*password:",
            # r".*Password:",
            r"3004-007 You entered an invalid login name or password",
            r"Open in progress",
            r"Open Completed.",
            TIMEOUT
        ]
        rm_cmd = f"rmvterm -m {managed_host} -p {lpar_name}"
        self.sendline(rm_cmd)
        i = self.expect(session_regex_array, timeout=login_timeout)
        # First phase
        if i == 0:
            mk_cmd = f"mkvterm -m {managed_host} -p {lpar_name}"
            self.sendline(mk_cmd)
            i = self.expect(session_regex_array, timeout=login_timeout)
            # ??
            self.linesep = "\n\r"
        if i == 5:
            i = self.expect(session_regex_array, timeout=login_timeout)
        if i == 6:
            i = self.expect(session_regex_array, timeout=login_timeout)
        if i == 2:
            self.sendline("%s" % user)
            i = self.expect(session_regex_array, timeout=login_timeout)
        if i == 3:
            self.sendline("%s" % password)
            i = self.expect(session_regex_array, timeout=login_timeout)
        # Second phase
        if i == 1:
            # login console success
            pass
        elif i == 0 or i == 2 or i == 3:
            self.close()
            raise ExceptionPxssh('bad password')
        elif i == 4:
            self.close()
            raise ExceptionPxssh('3004-007 You entered an invalid user name or password to login console.')
        elif i == 7:  # TIMEOUT
            self.close()
            raise ExceptionPxssh('Could not establish connection to lpar console')
        else:  # Unexpected
            self.close()
            raise ExceptionPxssh('unexpected login response')
        return True

    def logout_console(self, login_timeout=10):
        """
        退出Lpar控制台
        """
        session_regex_array = [
            self.PROMPT,
            r"[$#>]",
            #r"^(?:Console login: )",
            r"Console login:",
            TIMEOUT
        ]
        self.sendline("exit")
        i = self.expect(session_regex_array, timeout=login_timeout)
        if i == 0:
            self.sendline("exit")
            i = self.expect(session_regex_array, timeout=login_timeout)
        if i == 2:
            self.sendline("~.")
            # i = self.expect(session_regex_array, timeout=login_timeout)
        # if i == 1:
        #     self.sendline()
        #     i = self.expect(session_regex_array, timeout=login_timeout)
        # if i == 1:
        #     pass
        else:  # Unexpected
            self.close()
            raise ExceptionPxssh('unexpected logout response')
        return True

    def set_locale_lc_all(self, locale):
        """
        设置系统字符集（临时生效）
        export LANG=<locale> 或者 export LC_ALL=<locale>
        """
        self.sendline(f"export LC_ALL={locale}")
        self.expect([self.PROMPT, r'[#$>]'], timeout=10)

    def auto_set_unique_prompt(self, prompt=None):
        """
        We appear to be in.
        set shell prompt to something unique.
        """
        if prompt:
            self.PROMPT = prompt
        if not self.set_unique_prompt():
            self.close()
            raise ExceptionPxssh('could not set shell prompt '
                                 '(received: %r, expected: %r).' % (
                                     self.before, self.PROMPT,))
        return True

    def set_system_env(self):
        """
        关闭Linux中You have new mail in /var/spool/mail/root的提示（临时生效）
        unset MAILCHECK
        """
        # self.sendline(f"set +o history")
        self.sendline(f"export HISTSIZE=0")
        self.expect([self.PROMPT, r'[#$>]'], timeout=10)
        self.sendline(f"unset MAILCHECK")
        self.expect([self.PROMPT, r'[#$>]'], timeout=10)
        self.sendline(f"unset TERM")
        self.expect([self.PROMPT, r'[#$>]'], timeout=10)

# vi:ts=4:sw=4:expandtab:ft=python:
