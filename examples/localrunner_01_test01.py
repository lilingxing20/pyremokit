#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#
# 参数定义说明：
#   - required: 为"Y"表示此字段是必传参数，为"N"表示此字段是可选参数
#   - defaultvalue: 用于脚本导入平台时为参数表单设置默认值。当未给出defalutvalue时，默认为""
"""
#PARAMETER-NOTE-START#
{
  "version": "v1.0.0",
  "description": "测试脚本",
  "upParaStruct": {
    "note": "脚本输入参数",
    "required": "Y",
    "valueType": "OBJECT",
    "k1": {
      "note": "参数1",
      "required": "Y",
      "valueType": "STRING",
      "values": [
      ]
    }
  },
  "downParaStruct": {
    "note": "脚本输出参数",
    "required": "Y",
    "valueType": "OBJECT",
    "output": {
      "note": "结果信息",
      "required": "Y",
      "valueType": "OBJECT",
      "values": []
    }
  }
}
#PARAMETER-NOTE-END#
"""

import sys
import time
import json

from collections import OrderedDict
from pyremokit.cmdtool.localenv import LocalEnv
from pyremokit.cmdtool.localrunner import LocalRunner


def script_run():
    try:
        # 全部参数保存在 LocalEnv.params_json
        #   - 登录参数保存在 LocalEnv.login
        #   - 业务参数保存在 LocalEnv.parameter
        # parsescript=True时LocalEnv会校验脚本和参数,若出错则抛出异常信息
        # 解析脚本参数
        lenv = LocalEnv(parsescript=True, printtostdout=True)
        # 业务参数
        busparams = lenv.parameter
        print(busparams)

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
        filename = './tasklog/20231210.task.log'
        # stat, msg = lr.readinglogfile(filename, 10, None)
        stat, msg = lr.readinglogfile(filename, 10, print)
        # stat, msg = lr.tailf(filename, 10, print)
        print(stat, msg)
        time.sleep(5)
        lr.stopreadinglogfile()
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

