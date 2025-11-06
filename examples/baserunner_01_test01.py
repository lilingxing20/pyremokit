#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import json

from collections import OrderedDict

from pyremokit.baserunner import BaseRunner


def script_run():
    try:
        br = BaseRunner()

        # 业务参数
        busparams = br.env.parameter
        print(busparams)

        cmd = 'ls'
        br.runcmd(cmd)
        print(br.get_all_return())
        print(br.get_lastmsg())

        cmds = OrderedDict()
        cmds['cmd1'] = "ls"
        cmds['cmd2'] = "pwd"
        br.rundict(cmds)
        print(br.get_all_return())
        print(br.get_lastmsg())

    except Exception as e:
        print(f"Error: {e}")


if __name__ == '__main__':

    busiparam = {
        "scriptTaskId": "20231210",         # 脚本任务ID
        "scriptLogPath": "./tasklog",       # 脚本任务日志目录
        "genTaskLog": "Y",                  # 是否生成脚本任务日志
        "genReplyLog": "Y",                 # 是否生成脚本结果日志
        "genExpectLog": "Y",                # 是否生成终端交互日志
        "k1": "v1"
    }
    if len(sys.argv) <= 1:
        pstr = json.dumps(busiparam)
        print("# python %s '%s'" % (sys.argv[0], pstr))
        sys.argv.append(pstr)
    script_run()


""" 运行结果:
# python baserunner_01_test01.py '{"scriptTaskId": "20231210", "scriptLogPath": "./tasklog", "genTaskLog": "Y", "genReplyLog": "Y", "genExpectLog": "Y", "k1": "v1"}'
{'k1': 'v1'}
OrderedDict({'runcmd': ['ls']})
base runner run cmd success
OrderedDict({'runcmd': [], 'cmd1': 'ls', 'cmd2': 'pwd'})
base runner run dict success
"""
