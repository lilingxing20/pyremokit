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
import json

from collections import OrderedDict

from pyremokit.baseenv import BaseEnv
from pyremokit.baserunner import BaseRunner


def script_run():
    try:
        # 全部参数保存在BaseEnv.params_json
        #   - 登录参数保存在BaseEnv.login
        #   - 业务参数保存在BaseEnv.parameter
        # parsescript=True时BaseEnv会校验脚本和参数,若出错则抛出异常信息
        # 解析脚本参数
        benv = BaseEnv(parsescript=True, printtostdout=True)
        # 业务参数
        busparams = benv.parameter
        print(busparams)

        br = BaseRunner(envpointer=benv)
        br.connect()

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


""" 运行结果：
# python baserunner_01_test02.py '{"scriptTaskId": "20231210", "scriptLogPath": "./tasklog", "genTaskLog": "Y", "genReplyLog": "Y", "genExpectLog": "Y", "k1": "v1"}'
{'k1': 'v1'}
OrderedDict({'runcmd': ['ls']})
base runner run cmd success
OrderedDict({'runcmd': [], 'cmd1': 'ls', 'cmd2': 'pwd'})
base runner run dict success
"""
