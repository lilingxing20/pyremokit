#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
解析和校验参数格式
'''

import json

from base64 import b64encode
from pyremokit.baseenv import BaseEnv
from pyremokit.baseenv import NON_BUSI_PARAMETER


# 脚本中参数预定义标识符
SCRIPT_PARAM_BEGINSTR = "#PARAMETER-NOTE-START#"
SCRIPT_PARAM_ENDSTR = "#PARAMETER-NOTE-END#"


class PexpEnv(BaseEnv):
    """
    基础环境准备
    """

    def __init__(self,
                 checkparams=True,
                 parsescript=True,
                 logpath=None,
                 logfile=None,
                 printtostdout=False,
                 genreplylog=False,
                 gentasklog=False):
        """
        参数检查并格式化
        """
        super().__init__(logpath=logpath,
                         logfile=logfile,
                         printtostdout=printtostdout,
                         genreplylog=genreplylog,
                         gentasklog=gentasklog)
        self.login_list = []
        self.login_number = 0
        self.param_requried = {}

        if parsescript is True:
            try:
                # 从脚本中读取预定义的参数格式信息
                self.read_script_define_param()
                # 如果脚本中参数的定义格式错误，则抛出异常
                self.verify_script_define_param()
            except Exception as e:
                self.log(str(e))
                raise Exception("parse script define param exception: " + str(e)) from e
        else:
            self.define_param_json = {}

        if checkparams:
            # 脚本输入参数 BaseEnv.params_json
            # 校验脚本输入参数, 分类存储
            # self.login     保存登录方式，{'authMode':'', 'ip':'', 'port':'', 'username':'','password':''}
            # self.su_param  保存su信息, {'username':'', 'password':''}
            # self.parameter 保存实参，格式为实参的键值对{'key':value}
            self.check_script_input_param()

        # 打印关键但非敏感参数
        self.log(f'Log file: {self.logfile}', tasklog=False)
        self.log(f'Expect log to: {self.expectlog}', tasklog=False)
        if not self.login_list:
            self.log('No login parameters were passed in.', tasklog=False)
        for login_param in self.login_list:
            self.log('Login parameter: ', tasklog=False)
            self.log('  authMode: ' + str(login_param['authMode']), tasklog=False)
            self.log('  ip: ' + str(login_param['ip']), tasklog=False)
            self.log('  port: ' + str(login_param['port']), tasklog=False)
            self.log('  username: ' + str(login_param['username']), tasklog=False)
            pwd = str(login_param['password'])
            encodestr_pwd = b64encode(pwd.encode('utf-8')).decode()
            self.log('  password: ' + str(encodestr_pwd), tasklog=False)
            proxy_list = login_param.get('hostProxyList', [])
            if proxy_list:
                self.log('Login proxy host parameter: ', tasklog=False)
                for proxy_param in proxy_list:
                    self.log('  authMode: ' + str(proxy_param['authMode']), tasklog=False)
                    self.log('  ip: ' + str(proxy_param['ip']), tasklog=False)
                    self.log('  port: ' + str(proxy_param['port']), tasklog=False)
                    self.log('  username: ' + str(proxy_param['username']), tasklog=False)
                    pwd = str(proxy_param['password'])
                    encodestr_pwd = b64encode(pwd.encode('utf-8')).decode()
                    self.log('  password: ' + str(encodestr_pwd), tasklog=False)

        if self.su_param:
            self.log('Switch user parameter: ', tasklog=False)
            self.log('  username: ' + str(self.su_param['username']), tasklog=False)
            pwd = str(self.su_param['password'])
            encodestr_pwd = b64encode(pwd.encode('utf-8')).decode()
            self.log('  password: ' + str(encodestr_pwd), tasklog=False)
        else:
            self.log('No switch user parameters were passed in.', tasklog=False)

        if self.parameter:
            self.log('Business parameter: ', tasklog=False)
            for k, v in self.parameter.items():
                self.log(f'  {k}: {v}', tasklog=False)
        else:
            self.log('No business parameters were passed in.', tasklog=False)

    def init_down_param(self):
        """
        脚本输出参数格式
        """
        return {
            "status": "SUCCESS",
            "message": "脚本执行成功",
            "result": {}
        }

    def read_script_define_param(self):
        """
        读取脚本开头部分定义的参数信息
        """
        filestr = ""
        with open(self.scriptrealfile, "r", encoding="utf8") as fp:
            filestr = fp.read()
        index_begin = filestr.find(SCRIPT_PARAM_BEGINSTR)
        index_begin += len(SCRIPT_PARAM_BEGINSTR)
        index_end = filestr.find(SCRIPT_PARAM_ENDSTR)
        if (index_begin == -1) or (index_end == -1) or (index_end - index_begin < 100):
            raise Exception('There are no parameter definitions in the script!')
        param_def = filestr[index_begin: index_end]
        param_def = param_def.replace('#', '')
        param_def = param_def.strip(self.linesep)
        param_def = param_def.strip('\n')
        param_def = param_def.replace(self.linesep, "")
        param_def = param_def.replace(" ", "")
        self.define_param_json = json.loads(param_def)
        return self.define_param_json

    def _check_param_define(self, param_name, param_dict, param_key, param_val=None):
        """
        判断参数定义格式
        """
        if param_key not in param_dict:
            raise Exception('The key %s in %s not found!' % (param_key, param_name))
        if param_val:
            kv = param_dict[param_key]
            if str(kv).strip().upper() not in param_val:
                raise Exception('The value of %s in %s is not %s!' % (
                    param_key, param_name, param_val))

    def verify_script_define_param_values(self, param_name, param_values):
        """
        验证脚本中预定义参数的默认值信息格式是否正确
        """
        for param_value in param_values:
            for key in ["value", "defaultValue"]:
                self._check_param_define(param_name, param_value, key)

    def verify_script_define_login_proxy_param(self, proxy_param):
        """
        验证脚本中预定义登录参数中代理主机参数格式是否正确
        """
        for key in ["authMode", "ip", "port", "username", "password"]:
            self._check_param_define("upParaStruct.login.hostProxy", proxy_param, key)
            self._check_param_define(f"upParaStruct.login.hostProxy.{key}", proxy_param[key], "required", ["Y"])
            if proxy_param[key].get('values', False):
                self.verify_script_define_param_values(f"upParaStruct.login.hostProxy.{key}.values", proxy_param[key]['values'])

    def verify_script_define_login_param(self, login_param):
        """
        验证脚本中预定义登录参数格式是否正确
        """
        for key in ["authMode", "ip", "port", "username", "password"]:
            self._check_param_define("upParaStruct.login", login_param, key)
            self._check_param_define(f"upParaStruct.login.{key}", login_param[key], "required", ["Y"])
            if login_param[key].get("valumes", False):
                self.verify_script_define_param_values(f"upParaStruct.login.{key}.values", login_param[key]['values'])
        if login_param.get("role", False):
            # self._check_param_define("upParaStruct.login", login_param, "role")
            self._check_param_define("upParaStruct.login.role", login_param['role'], "required", ["Y", "N"])
            if login_param['role']['required'].upper() == "Y":
                self._check_param_define("upParaStruct.login.role", login_param['role'], "values")
                self.verify_script_define_param_values("upParaStruct.login.role.values", login_param['role']['values'])
        if login_param.get("hostProxy", False):
            # self._check_param_define("upParaStruct.login", login_param, "hostProxy")
            proxy_param = login_param['hostProxy']
            self._check_param_define("upParaStruct.login.hostProxy", proxy_param, "required", ["Y", "N"])
            if proxy_param['required'].upper() == "Y":
                self.verify_script_define_login_proxy_param(proxy_param)

    def verify_script_define_su_param(self, su_param):
        """
        验证脚本中预定义SU切换用户参数格式是否正确
        """
        for key in ["username", "password"]:
            self._check_param_define("upParaStruct.suUser", su_param, key)
            self._check_param_define(f"upParaStruct.suUser.{key}", su_param[key], "required", ["Y"])
            if su_param[key].get('values', False):
                self.verify_script_define_param_values(f"upParaStruct.suUser.{key}.values", su_param[key]['values'])

    def verify_script_define_param(self):
        """
        验证脚本中预定义参数格式是否正确
        参数为json格式的字符串, 包括:
          upParaStruct: <login>/[suUser]/[other parameter]/[scriptTaskId]
            - 必须参数login保存登录信息
            - 可选参数suUser保存su信息
            - 可选参数other parameter保存业务参数信息
            - 可选参数scriptTaskId保存脚本任务ID信息
            - 可选参数scriptLogPath保存脚本任务ID信息
            - 可选参数genTaskLog保存脚本是否生成任务日志信息
            - 可选参数genReployLog保存脚本是否生成结果日志信息
          downParaStruct: <status>/<message>/<result>
        """
        # 脚本预定义参数格式信息JSON对象
        jsonobj = self.define_param_json

        # # 验证脚本参数格式版本信息
        # self._check_param_define("ScriptParameter", jsonobj, "version")

        # 验证脚本上行参数 upParaStruct
        self._check_param_define("ScriptParameter", jsonobj, "upParaStruct")
        up_param = jsonobj['upParaStruct']

        # 验证脚本上行参数 upParaStruct 中登录参数 login
        self._check_param_define("upParaStruct", up_param, "required", ["Y"])
        self._check_param_define("upParaStruct", up_param, "valueType", ["OBJECT"])
        self._check_param_define("upParaStruct", up_param, "login")
        login_param = up_param['login']
        self._check_param_define("upParaStruct", login_param, "valueType", ["OBJECT", "ARRAY"])
        self.verify_script_define_login_param(login_param)

        # 验证脚本上行参数 upParaStruct 中切换用户参数 suUser
        if up_param.get("suUser", False):
            # self._check_param_define("upParaStruct.", up_param, "suUser")
            su_param = up_param['suUser']
            self._check_param_define("upParaStruct.suUser", su_param, "required", ["Y", "N"])
            self._check_param_define("upParaStruct.suUser", su_param, "valueType", ["OBJECT"])
            if su_param['required'].upper() == 'Y':
                self.verify_script_define_su_param(su_param)

        # 验证脚本上行参数upParaStruct 中业务参数
        for k, v in up_param.items():
            if k in NON_BUSI_PARAMETER:
                continue
            self._check_param_define(f"upParaStruct.{k}", v, "required", ["Y", "N"])
            if str(v['required']).strip().upper() == "Y":
                self.param_requried[k] = ""
            if v.get("values", False):
                self.verify_script_define_param_values(f"upParaStruct.{k}.values", v['values'])

        # 验证脚本下行参数 downParaStruct
        self._check_param_define("ScriptParameter", jsonobj, "downParaStruct")

    def _check_login_proxy_param(self, proxy_param):
        """
        验证脚本参数中登录参数中 代理主机参数 信息是否完整
        """
        for key in ["authMode", "ip", "port", "username", "password"]:
            self._check_param_define("upParaStruct.login.hostProxy", proxy_param, key)

    def _check_login_param(self, login_param):
        """
        验证脚本参数中 登录参数 信息是否完整
        """
        for key in ["authMode", "ip", "port", "username", "password"]:
            self._check_param_define("upParaStruct.login", login_param, key)
        proxy_param = login_param.get("hostProxy")
        if proxy_param:
            login_param['hostProxyList'] = []
            if isinstance(proxy_param, dict):
                self._check_login_proxy_param(proxy_param)
                login_param['hostProxyList'].append(proxy_param)
            elif isinstance(proxy_param, list):
                for _proxy_param in proxy_param:
                    self._check_login_proxy_param(_proxy_param)
                    login_param['hostProxyList'].append(_proxy_param)

    def check_script_input_param(self):
        """
        校验脚本输入参数
        """
        paramjson = self.params_json
        # 使用参数之前需先通过格式较验
        login_param = paramjson.get('login', False)
        if not login_param:
            raise Exception('Missing parameter login !')
        if isinstance(login_param, dict):
            self.login = login_param
            self.login_list.append(login_param)
            self._check_login_param(login_param)
        elif isinstance(login_param, list):
            self.login_list = login_param
            for _login in login_param:
                self._check_login_param(_login)
            self.login = self.login_list[0]
        else:
            raise Exception('Parameter upParaStruct.login format unknown !')
        self.login_number = len(self.login_list)

        su_param = paramjson.get('suUser', False)
        if su_param:
            if not su_param.get('username', False):
                raise Exception('Missing parameter suUser.username !')
            if not su_param.get('password', False):
                raise Exception('Missing parameter suUser.password !')
            self.su_param = su_param

        # # 保留原始json参数格式，整理业务参数
        # for k, v in paramjson.items():
        #     if k in NON_BUSI_PARAMETER:
        #         continue
        #     self.parameter[k] = v

        # 检查必须业务参数是否已传参
        for key in self.param_requried:
            if key not in self.parameter:
                raise Exception(f'Missing business upParamStruct.{key} !')

# vi:ts=4:sw=4:expandtab:ft=python:
