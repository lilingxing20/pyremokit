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


class LocalEnv(BaseEnv):
    """
    基础环境准备
    """

    def __init__(self,
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
                         gentasklog=gentasklog
                         )
        self.param_requried = {}

        if parsescript is True:
            try:
                # 从脚本中读取预定义的参数格式信息
                self.read_script_define_param()
                # 如果脚本中参数的定义格式错误，则抛出异常
                self.verify_script_define_param()
            except Exception as e:
                self.log(str(e))
                raise Exception(str(e)) from e
        else:
            self.define_param_json = {}

        # 脚本输入参数 BaseEnv.params_json
        # 校验脚本输入参数, 分类存储
        # self.su_param   保存su信息, {'su_user':'', 'su_password':''}
        # self.parameter 保存实参，格式为实参的键值对{'key':value}
        self.check_script_input_param()

        # 打印关键但非敏感参数
        self.log('Log file: ' + self.logfile, tasklog=False)
        if self.su_param.get('su_user'):
            self.log('Switch user parameter: ', tasklog=False)
            self.log('  su_user: ' + str(self.su_param.get('su_user')), tasklog=False)
            pwd = str(self.su_param['su_password'])
            encodestr_pwd = b64encode(pwd.encode('utf-8')).decode()
            self.log('  su_password: ' + str(encodestr_pwd), tasklog=False)
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

    def verify_script_define_su_param(self, su_param):
        """
        验证脚本中预定义SU切换用户参数格式是否正确
        """
        for key in ["su_user", "su_password"]:
            self._check_param_define("upParaStruct.suUser", su_param, key)
            self._check_param_define(f"upParaStruct.suUser.{key}", su_param[key], "required", ["Y"])
            if su_param[key].get('values', False):
                self.verify_script_define_param_values(f"upParaStruct.suUser.{key}.values", su_param[key]['values'])

    def verify_script_define_param(self):
        """
        验证脚本中预定义参数格式是否正确
        参数为json格式的字符串, 包括:
          upParaStruct: [suUser]/[other parameter]/[scriptTaskId]
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

    def check_script_input_param(self):
        """
        校验脚本输入参数
        """
        paramjson = self.params_json
        # 使用参数之前需先通过格式较验
        su_param = paramjson.get('suUser', False)
        if su_param:
            if not su_param.get('su_user', False):
                raise Exception('Missing parameter suUser.su_user !')
            if not su_param.get('su_password', False):
                raise Exception('Missing parameter suUser.su_password !')
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
