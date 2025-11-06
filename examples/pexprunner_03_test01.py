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
  "version": "v3.0.0",
  "description": "场景03: 同时登录多个节点",
  "upParaStruct": {
    "note": "脚本输入参数",
    "shortNote": "脚本输入参数",
    "required": "Y",
    "valueType": "OBJECT",
    "login": {
      "note": "登录参数",
      "shortNote": "登录参数",
      "valueType": "ARRAY",
      "required": "Y",
      "authMode": {
        "note": "授权模式 PASSWORD",
        "shortNote": "授权模式",
        "propertyType": "BUILT-IN",
        "display": "N",
        "required": "Y",
        "valueType": "ENUM",
        "encrypt": "N",
        "valueNumber": "ONE",
        "values": [
          {
            "value": "PASSWORD",
            "defaultValue": true,
            "desc": "密码认证"
          },
          {
            "value": "KEY",
            "defaultValue": false,
            "desc": "密钥认证"
          }
        ]
      },
      "ip": {
        "note": "主机登录IP地址",
        "shortNote": "主机地址",
        "propertyType": "BUILT-IN",
        "display": "N",
        "required": "Y",
        "valueType": "STRING",
        "encrypt": "N",
        "valueNumber": "ONE",
        "values": []
      },
      "port": {
        "note": "主机连接端口",
        "shortNote": "主机端口",
        "propertyType": "BUILT-IN",
        "display": "N",
        "required": "Y",
        "valueType": "STRING",
        "encrypt": "N",
        "valueNumber": "ONE",
        "values": [
          {
            "value": "22",
            "defaultValue": true,
            "desc": "端口22"
          }
        ]
      },
      "username": {
        "note": "主机登录用户",
        "shortNote": "登录用户",
        "propertyType": "BUILT-IN",
        "display": "N",
        "required": "Y",
        "valueType": "STRING",
        "encrypt": "N",
        "valueNumber": "ONE",
        "values": [
          {
            "value": "root",
            "defaultValue": false,
            "desc": "主机登陆用户"
          }
        ]
      },
      "password": {
        "note": "主机登录用户密码",
        "shortNote": "密码",
        "propertyType": "BUILT-IN",
        "display": "N",
        "required": "Y",
        "valueType": "STRING",
        "encrypt": "Y",
        "valueNumber": "ONE",
        "values": []
      }
    },
    "nic_name": {
      "note": "网卡名",
      "shortNote": "网卡名",
      "propertyType": "ORDINARY",
      "display": "Y",
      "required": "Y",
      "valueType": "STRING",
      "encrypt": "N",
      "valueNumber": "ONE",
      "values": [
      ]
    }
  },
  "downParaStruct": {
    "note": "脚本输出参数",
    "shortNote": "脚本输出参数",
    "valueType": "OBJECT",
    "required": "Y",
    "nic_info": {
      "note": "网卡信息",
      "shortNote": "网卡信息",
      "propertyType": "ORDINARY",
      "display": "Y",
      "required": "Y",
      "valueType": "OBJECT",
      "encrypt": "N",
      "valueNumber": "MANY",
      "values": []
    }
  }
}
#PARAMETER-NOTE-END#
"""
#SCRIPT-CONTENT-START#

import base64
import copy
import json
import sys
import time

from pyremokit.cmdtool.pexpenv import PexpEnv
from pyremokit.cmdtool.pexprunner import PexpRunner


# 返回值
script_result = {
    "status": "SUCCESS",
    "exception": "",
    "message": "查询Linux系统网卡信息成功",
    "result": {
        "nic_info": {}
    }
}


def report_progress_info(env, ops_log_url, task_progress, task_info, log_type=3):
    """
    上报软件部署进度
    log_type:
      - 1: 仅更新 进度
      - 2: 仅更新 日志
      - 3: 同时更新 进度 和 日志
    """
    now_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    progress = "%3s" % task_progress
    msg = f"{now_str} [{progress}%] {task_info}"
    if str(ops_log_url).startswith('http'):
        msg_b64 = base64.b64encode(msg.encode('utf-8'))
        env.report(task_progress, str(msg_b64).split("'")[1], report_url=ops_log_url)
    elif str(ops_log_url).startswith('print'):
        print(msg)
    else:
        pass


def get_all_nic(pr):
    r"""
    查询系统所有网卡
    # ip -o link show
    1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN mode DEFAULT group default qlen 1000\    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    2: ens192: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1450 qdisc fq_codel state UP mode DEFAULT group default qlen 1000\    link/ether 00:50:56:b8:61:b9 brd ff:ff:ff:ff:ff:ff
    """
    nic_names = []
    pr.runcmd("ip -o link show")
    if pr.get_lastcode() != 0:
        raise Exception("查询网卡名异常: %s" % pr.get_lastmsg())
    for _line in pr.get_cmd_return('runcmd'):
        line = _line.strip()
        if not line:
            continue
        nic_names.append(line.split()[1].strip())
    return nic_names


def get_nic_info(pr, nic_name):
    r"""
    查询网卡信息
    # ip -o link show ens192
    2: ens192: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1450 qdisc fq_codel state UP mode DEFAULT group default qlen 1000\    link/ether 00:50:56:b8:61:b9 brd ff:ff:ff:ff:ff:ff
    """
    nic_info = {}
    pr.runcmd(f"ip -o link show {nic_name}")
    if pr.get_lastcode() != 0:
        raise Exception("查询网卡信息异常: %s" % pr.get_lastmsg())
    for _line in pr.get_cmd_return('runcmd'):
        line = _line.strip()
        if not line:
            continue
        arr = line.split()
        nn = arr[1].strip().strip(":")
        if nn != nic_name:
            continue
        nic_info["name"] = nn
        nic_info["mtu"] = arr[4]
        nic_info["status"] = arr[8]
        nic_info["mac"] = arr[16]
    return nic_info


def script_run():
    try:
        # 全部参数保存在PexpEnv.params_json
        #   - 登录参数保存在PexpEnv.login
        #   - 业务参数保存在PexpEnv.parameter
        # parsescript=True时PexpEnv会校验脚本和参数,若出错则抛出异常信息
        # 解析脚本参数
        penv = PexpEnv(parsescript=True, printtostdout=False)

        # 登陆参数
        login_list = penv.login_list
        # 业务参数
        busparams = penv.parameter
        nic_name = busparams['nic_name']

        # 脚本运行上报进度信息接口URL参数
        ops_log_url = busparams.get('OPS_LOG_URL')
        # ops_review_url = busparams.get('OPS_REVIEW_URL')

        report_progress_info(penv, ops_log_url, 1, "######## -- %s -- Test Pexprunner. ########" % time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))
        # 参数值检查
        report_progress_info(penv, ops_log_url, 5, "Start checking the parameters.")
        if not nic_name:
            raise Exception("网卡名参数nic_name空值异常")
        report_progress_info(penv, ops_log_url, 10, "The parameter check is OK.")

    except Exception as e:
        msg = 'The parameter check fails: %s' % str(e)
        penv.reply("FAIL", "-1", msg)
        # raise Exception(msg)
        script_result['status'] = "ERROR"
        script_result['exception'] = "ParameterException"
        script_result['message'] = msg
        penv.set_tasklog_end()
        return 1, script_result

    try:
        report_progress_info(penv, ops_log_url, 15, "Start connecting to the remote host.")
        # 连接远程主机
        prs = []
        for login in login_list:
            penv.login = login
            pr = PexpRunner(envpointer=penv, resetpromt=True, getrtncode=True, timeout=300)
            ret = pr.connect()
            if ret:
                msg = 'Failed to connect to remote host: ' + pr.login['ip'] + ', msg: ' + pr.get_lastmsg() + ';'
                pr.log(msg)
                raise Exception(msg)
            prs.append(pr)
        report_progress_info(penv, ops_log_url, 20, "The remote host was successfully connected.")

        # 查询网卡信息
        report_progress_info(penv, ops_log_url, 80, f"Get nic {nic_name} info")
        for pr in prs:
            nic_info = get_nic_info(pr, nic_name)
            script_result['result']['nic_info'].update({pr.login['ip']: nic_info})

        report_progress_info(penv, ops_log_url, 100, "######## -- %s -- Finish Run Test Pexprunner. ########" % time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()))

        # 清理expect日志
        pr.expect_logfile_delete()

        # 脚本返回值
        penv.reply("SUCCESS", "0", "执行成功", script_result)
        return 0, script_result

    except Exception as e:
        msg = 'Exception occurred during script execution: %s' % str(e)
        penv.reply("FAIL", "-1", msg)
        # raise Exception(msg)
        script_result['status'] = "ERROR"
        script_result['exception'] = "ExecuteException"
        script_result['message'] = msg
        return 2, script_result

    finally:
        for pr in prs:
          pr.close()
        penv.set_tasklog_end()


if __name__ == "__main__":
    busiparam = {
            "OPS_LOG_URL": "print",
            "scriptTaskId": "20231210",         # 脚本任务ID
            "scriptLogPath": "./tasklog",       # 脚本任务日志目录
            "genTaskLog": "Y",                  # 是否生成脚本任务日志
            "genReplyLog": "Y",                 # 是否生成脚本结果日志
            "genExpectLog": "Y",                # 是否生成终端交互日志
            "nic_name": "enp0s1"
            }
    pjson1 = {
        "login": [
            {
                "authMode": "PASSWORD",
                "ip": "192.168.64.10",
                "port": 22,
                "username": "root",
                "password": "123456",
            },
            {
                "authMode": "PASSWORD",
                "ip": "192.168.64.15",
                "port": 22,
                "username": "root",
                "password": "root",
            }
        ]
    }

    ss = sys.argv.pop()
    if ss == 'test':
        pjson = pjson1
        pjson.update(busiparam)
        pstr = json.dumps(pjson)
        print("# python %s '%s'" % (sys.argv[0], pstr))
        sys.argv.append(pstr)
    else:
        sys.argv.append(ss)

    ret_code, ret_out = script_run()
    print(json.dumps(ret_out, indent=2, ensure_ascii=False, default=str))
    sys.exit(ret_code)

#SCRIPT-CONTENT-END#
''' 运行结果：
# python pexprunner_03_test01.py '{"login": [{"authMode": "PASSWORD", "ip": "192.168.64.10", "port": 22, "username": "root", "password": "123456"}, {"authMode": "PASSWORD", "ip": "192.168.64.15", "port": 22, "username": "root", "password": "root"}], "OPS_LOG_URL": "print", "scriptTaskId": "20231210", "scriptLogPath": "./tasklog", "genTaskLog": "Y", "genReplyLog": "Y", "genExpectLog": "Y", "nic_name": "enp0s1"}'
2025-11-06 23:07:08 [  1%] ######## -- 2025-11-06 23:07:08 -- Test Pexprunner. ########
2025-11-06 23:07:08 [  5%] Start checking the parameters.
2025-11-06 23:07:08 [ 10%] The parameter check is OK.
2025-11-06 23:07:08 [ 15%] Start connecting to the remote host.
2025-11-06 23:07:13 [ 20%] The remote host was successfully connected.
2025-11-06 23:07:13 [ 80%] Get nic enp0s1 info
2025-11-06 23:07:19 [100%] ######## -- 2025-11-06 23:07:19 -- Finish Run Test Pexprunner. ########
{
  "status": "SUCCESS",
  "exception": "",
  "message": "查询Linux系统网卡信息成功",
  "result": {
    "nic_info": {
      "192.168.64.10": {
        "name": "enp0s1",
        "mtu": "1500",
        "status": "UP",
        "mac": "ae:e3:ac:cc:f7:b4"
      },
      "192.168.64.15": {
        "name": "enp0s1",
        "mtu": "1500",
        "status": "UP",
        "mac": "16:7c:df:f1:fc:de"
      }
    }
  }
}
'''
# vi:ts=4:sw=4:expandtab:ft=python:
