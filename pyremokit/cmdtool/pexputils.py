#!/usr/bin/env python
# -*- coding:utf-8 -*-
#
## PEXPRunner扩展类

import os

from pyremokit.cmdtool.pexprunner import PEXPRunner


class PEXPUtils(PEXPRunner):
    """
    PEXPRunner扩展类
    """

    def change_own(self, user, group, file_or_dir):
        """
        更改文件所有者和组
        """
        self.runcmd(f"chown -R {user}:{group} {file_or_dir}")
        if self.getrtncode and self.get_lastcode() != 0:
            msg = self.get_lastmsg()
            raise Exception('更改文件所有者和组错误: %s' % msg)

    def change_mod(self, acl, file_or_dir):
        """
        更改访问控制列表
        """
        self.runcmd(f"chmod -R {acl} {file_or_dir}")
        if self.getrtncode and self.get_lastcode() != 0:
            msg = self.get_lastmsg()
            raise Exception('更改访问控制列表错误: %s' % msg)

    def make_dir(self, dir_name):
        """
        创建目录
        """
        self.runcmd("mkdir -p " + dir_name)
        if self.getrtncode and self.get_lastcode() != 0:
            msg = self.get_lastmsg()
            raise Exception('创建目录错误: %s' % msg)

    def wget_download_file(self, url, store_path):
        """
        使用wget工具下载安装包文件
        """
        self.runcmd(f"wget -c --no-cookie --no-check-certificate --progress=dot -e dotbytes=10M {url} -P {store_path}")
        if self.getrtncode and self.get_lastcode() != 0:
            msg = self.get_lastmsg()
            raise Exception('使用wget下载文件 %s 错误: %s' % (url, msg))
        return "/".join([store_path, url.split('/')[-1]])

    def curl_download_file(self, url, store_path, file_name=None):
        """
        使用curl工具下载安装包文件
        """
        if not file_name:
            fname = url.split('/')[-1]
        else:
            fname = file_name
        store_fpath = "/".join([store_path, fname])
        self.runcmd(f"curl -C- -s -S -o {store_fpath} {url}")
        if self.getrtncode and self.get_lastcode() != 0:
            msg = self.get_lastmsg()
            raise Exception('使用curl下载文件 %s 错误: %s' % (url, msg))
        return store_fpath

    def ftp_download_file(self, server, user, passwd, target_fpath, store_path):
        """
        使用ftp工具下载安装包文件
        """
        l_fname = target_fpath.split('/')[-1]
        l_fpath = "/".join([store_path, l_fname])
        tmp_sh_file = "/tmp/ftpdownload_93ec2cb9.sh"
        # 创建ftp下载脚本
        cmddict = OrderedDict()
        cmddict['cmd00'] = f"echo '#!/usr/bin/ksh' >{tmp_sh_file}"
        cmddict['cmd01'] = f"echo 'ftp -v -n {server}<<EOF' >>{tmp_sh_file}"
        cmddict['cmd02'] = f"echo 'user {user} {passwd}' >>{tmp_sh_file}"
        cmddict['cmd03'] = f"echo 'binary' >>{tmp_sh_file}"
        cmddict['cmd04'] = f"echo 'lcd {store_path}' >>{tmp_sh_file}"
        cmddict['cmd05'] = f"echo 'prompt' >>{tmp_sh_file}"
        cmddict['cmd06'] = f"echo 'mget {target_fpath}' >>{tmp_sh_file}"
        cmddict['cmd07'] = f"echo 'bye' >>{tmp_sh_file}"
        cmddict['cmd08'] = f"echo 'EOF' >>{tmp_sh_file}"
        cmddict['cmd09'] = f"echo 'echo \"ftp mget successfully\"' >>{tmp_sh_file}"
        cmddict['cmd10'] = f"echo 'rm -f $0' >>{tmp_sh_file}"
        cmddict['cmd11'] = f"echo 'test -f {l_fpath}' >>{tmp_sh_file}"
        # cmddict['cmd12'] = f"chmod +x {tmp_sh_file}"
        self.rundict(cmddict)
        # 执行ftp下载脚本
        self.runcmd(f"ksh {tmp_sh_file}")
        if self.get_lastcode() != 0:
            raise Exception('使用ftp下载文件 %s 错误: %s' % (target_fpath, self.get_lastmsg()))
        return l_fpath

    def upload_file_to_remote(self, pkg_url, dest_path, dest_fname=None, pkg_store_path=None):
        """
        从部署节点上传安装包到被部署节点
        """
        remote_ip = self.login['host_ip']
        remote_port = self.login['host_port']
        remote_user = self.login['host_user']
        remote_pswd = self.login['host_password']
        if not pkg_store_path:
            pkg_store_path = os.environ.get("PKG_STORE_PATH", '/cmp/packages/')
        pkg_fname = pkg_url.split('/')[-1]
        if not dest_fname:
            dest_fname = pkg_fname
        local_file = pkg_store_path + '/' + pkg_fname
        remote_file = dest_path + '/' + dest_fname
        if not os.path.exists(local_file):
            raise Exception('软件仓库缺少文件: %s' % pkg_fname)
        ret = self.scp_upload(local_file, remote_file, remote_ip, remote_user, remote_pswd, remote_port=remote_port, timeout=1800)
        print(ret)
        if ret.find('100%') > -1:
            self.log("Upload file %s to remote node %s success." % (pkg_fname, remote_ip))
        else:
            raise Exception('上传文件 %s 异常: %s' % (pkg_fname, ret))
        return remote_file

    def unpack_pkg(self, pkg_file, store_path, dest_path=None):
        """
        解压软件包，根据文件后缀，适配解压方式
        """
        src_file = '/'.join([store_path, pkg_file])
        if not dest_path:
            dest_path = store_path
        if pkg_file.endswith("tar"):
            unpkg_cmd = f"tar -xf {src_file} -C {dest_path}"
        elif pkg_file.endswith("tar.gz"):
            unpkg_cmd = f"tar -zxf {src_file} -C {dest_path}"
        elif pkg_file.endswith("zip"):
            unpkg_cmd = f"unzip -q -o {src_file} -d {dest_path}"
        else:
            raise Exception('不支持解压(%s)包，请检查环境配置!' % pkg_file)
        self.runcmd(unpkg_cmd)
        if self.get_lastcode() != 0:
            raise Exception('解压包(%s)错误: %s' % (pkg_file, self.get_lastmsg()))

    def cleanup_dirs_files(self, files):
        """
        清理文件
        """
        pre_del_files = []
        for _f in files:
            f = _f.rstrip('/')
            if not f.startswith('/'):
                continue
            if f in ['/', '/home', '/root', '/usr', '/var', '/tmp', '/opt', '*']:
                continue
            pre_del_files.append(f)
        if pre_del_files:
            self.runcmd("rm -rf %s" % " ".join(pre_del_files))

# vi:ts=4:sw=4:expandtab:ft=python:
