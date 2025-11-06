#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#SCRIPT-CONTENT-START#

import json
import sys
import time

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
        pr = PexpRunner(resetpromt=True, getrtncode=True, timeout=300)

        # 业务参数
        nic_name = pr.env.parameter['nic_name']

        pr.report(1, "######## -- %s -- Test Pexprunner. ########" % time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()), tostdout=True)
        # 参数值检查
        pr.report(5, "Start checking the parameters.", tostdout=True)
        if not nic_name:
            raise Exception("网卡名参数nic_name空值异常")
        pr.report(10, "The parameter check is OK.", tostdout=True)

        pr.report(15, "Start connecting to the remote host.", tostdout=True)
        # 连接远程主机
        ret = pr.connect()
        if ret:
            msg = 'Failed to connect to remote host: ' + pr.login['ip'] + ', msg: ' + pr.get_lastmsg() + ';'
            pr.log(msg)
            raise Exception(msg)
        pr.report(20, "The remote host was successfully connected.", tostdout=True)

        # 查询网卡信息
        pr.report(80, f"Get nic {nic_name} info.", tostdout=True)
        nic_info = get_nic_info(pr, nic_name)
        script_result['result']['nic_info'] = nic_info

        pr.report(100, "######## -- %s -- Finish Run Test Pexprunner. ########" % time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()), tostdout=True)

        # 清理expect日志 pexprunner>=4.0.0.dev111
        # pr.expect_logfile_delete()

        # 脚本返回值
        pr.reply("SUCCESS", "0", "执行成功", script_result)
        return 0, script_result

    except Exception as e:
        msg = 'Exception occurred during script execution: %s' % str(e)
        pr.reply("FAIL", "-1", msg)
        # pr.log(msg)
        # raise Exception(msg)
        script_result['status'] = "ERROR"
        script_result['exception'] = "ExecuteException"
        script_result['message'] = msg
        return 2, script_result

    finally:
        pr.close()
        pr.set_tasklog_end()


if __name__ == "__main__":
    busiparam = {
            "scriptTaskId": "20231210",         # 脚本任务ID
            "scriptLogPath": "./tasklog",       # 脚本任务日志目录
            "genTaskLog": "Y",                  # 是否生成脚本任务日志
            "genReplyLog": "Y",                 # 是否生成脚本结果日志
            "genExpectLog": "Y",                # 是否生成终端交互日志
            "nic_name": "enp0s1"
            }
    pjson1 = {
        "login": {
            "authMode": "PASSWORD",
            "ip": "192.168.64.10",
            "port": 22,
            "username": "root",
            "password": "123456",
        }
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
# python pexprunner_01_test01.py '{"login": {"authMode": "PASSWORD", "ip": "192.168.64.10", "port": 22, "username": "root", "password": "123456"}, "scriptTaskId": "20231210", "scriptLogPath": "./tasklog", "genTaskLog": "Y", "genReplyLog": "Y", "genExpectLog": "Y", "nic_name": "enp0s1"}'
2025-11-06_21:35:12.317029 [  1.00%] ######## -- 2025-11-06 21:35:12 -- Test Pexprunner. ########
2025-11-06_21:35:12.317087 [  5.00%] Start checking the parameters.
2025-11-06_21:35:12.317139 [ 10.00%] The parameter check is OK.
2025-11-06_21:35:12.317189 [ 15.00%] Start connecting to the remote host.
2025-11-06_21:35:25.601678 [ 20.00%] The remote host was successfully connected.
2025-11-06_21:35:25.602121 [ 80.00%] Get nic enp0s1 info.
2025-11-06_21:35:28.814420 [100.00%] ######## -- 2025-11-06 21:35:28 -- Finish Run Test Pexprunner. ########
{
  "status": "SUCCESS",
  "exception": "",
  "message": "查询Linux系统网卡信息成功",
  "result": {
    "nic_info": {
      "name": "enp0s1",
      "mtu": "1500",
      "status": "UP",
      "mac": "ae:e3:ac:cc:f7:b4"
    }
  }
}
'''
# vi:ts=4:sw=4:expandtab:ft=python:
