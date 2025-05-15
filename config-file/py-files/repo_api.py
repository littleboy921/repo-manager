from db_config import repo_conf_info_db,repo_sync_info_db,pshared_db
from class_define import DebRepoInfo,SyncObjInfo,NodeSyncObjStatus
from common_func.to_abs_path import to_abs_path
from common_func.render_tpl import render_tpl
from common_func.get_self_id import get_self_id
from common_func.deb_repo_update import deb_repo_update
from func_define import add_new_deb_repo

from flask import Flask,request,redirect,jsonify,Blueprint,send_file,flash,url_for,render_template,current_app
from sqlalchemy import and_
import os, time
import sys
import pathlib
import mimetypes
import posixpath
from werkzeug.utils import secure_filename
from typing import List, Tuple, Dict
import re
import pathvalidate 
import shutil
import urllib.parse
import subprocess
import urllib.parse

repo_api=Blueprint('repo_api',__name__)
#设置正确的时区
os.environ['TZ'] = 'Asia/Shanghai'  
time.tzset() 

#仓库配置文件位置绝对路径
current_dir = os.path.dirname(os.path.abspath(__file__))
log_file_dir = os.path.join(current_dir, '../logs/')
repo_config_file = os.path.join(current_dir,"repo-manager-conf.yml")

# 通过后缀判断mime类型
if not mimetypes.inited:
    mimetypes.init()  # try to read system mime.types
extensions_map = mimetypes.types_map.copy()
extensions_map.update({
    '': 'application/octet-stream',  # Default
    '.py': 'text/plain;charset=utf-8',
    '.c': 'text/plain;charset=utf-8',
    '.h': 'text/plain;charset=utf-8',
    '.txt': 'text/plain;charset=utf-8',
    '.conf': 'text/plain;charset=utf-8',
    '.sh': 'text/plain;charset=utf-8',
    '.md': 'text/markdown;charset=utf-8',
    '.jpeg,.jpg': 'image/jpeg',
    '.log': 'text/plain;charset=utf-8',
})

# 猜测文件类型
def guess_type(filepath: str) -> Tuple[str, str]:
    """Guess the type of a file.
    Argument is a PATH (a filename).
    Return value is a string of the form type/subtype,
    usable for a MIME Content-type header.
    The default implementation looks the file's extension
    up in the table self.extensions_map, using application/octet-stream
    as a default; however it would be permissible (if
    slow) to look inside the data to make a better guess.
    """
    if os.path.islink(filepath):
        islink = os.readlink(filepath)
    else:
        islink = ''
    # 判断文件为目录还是普通文件
    if os.path.isfile(filepath):
        basename, ext = posixpath.splitext(filepath)
        if ext in extensions_map:
            return extensions_map[ext], islink
        ext = ext.lower()
        if ext in extensions_map:
            return extensions_map[ext], islink
        else :
            return extensions_map[''], islink
    elif os.path.isdir(filepath):
        return 'dir', islink
    else:
        return 'empty_link', islink

#  使用列表推导式去重列表元素
def remove_list_duplicates(lst: List) -> List:
    unique_list = []
    [unique_list.append(item) for item in lst if item not in unique_list]
    return unique_list

    
@repo_api.route('/file_list/',methods=['GET'])
def get_file_list():
    dir_path=request.args.get('path')
    # 去掉路径开头的/
    if dir_path and dir_path[0] == '/':
        dir_path=dir_path[1:]
    abs_dir_path = os.path.normpath(os.path.join(os.getcwd(),dir_path))
    #print(os.getcwd())
    #print(f"function get_file_list abs_dir_path:{abs_dir_path}")
    if not os.path.exists(abs_dir_path):
        return jsonify({'code':1,'msg':'ERROR: Path not exists!'})
    if not os.path.isdir(abs_dir_path):
        return jsonify({'code':2,'msg':'ERROR: This path is not directory!'})
    current_dir_list=os.listdir(abs_dir_path)
    sorted_file_list = sorted(current_dir_list)
    file_info_list=[]
    count=0
    for filename in sorted_file_list:
        abs_file_path=os.path.join(abs_dir_path,filename)
        filetype,islink =guess_type(abs_file_path)
        # 如果是链接文件
        if islink == True:
            # 如果链接所指向的文件不存在，则返回链接文件本身的信息
            if not os.path.exists(abs_file_path):
                st = os.lstat(abs_file_path)
            else:
                st = os.stat(abs_file_path)
        # 如果是普通文件
        else:
            st = os.stat(abs_file_path)
        fsize = st.st_size
        fmtime = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(st.st_mtime))
        file_info_dict={
            "file_type": filetype,
            "file_name": filename, 
            "file_size": fsize,
            "file_mtime": fmtime,
            "islink": islink
        }
        file_info_list.append(file_info_dict)
        count=count+1
    return jsonify({'code':0,'msg':'yes','count':count,'data':file_info_list})

@repo_api.route('/file_contents/',methods=['GET'])
def get_file_contents():
    file_path=request.args.get('path','')
    is_logfile=request.args.get('is_logfile','0')
    # 去掉路径开头的/
    if file_path and file_path[0] == '/':
        file_path=file_path[1:] 
    # 转换为绝对路径
    if is_logfile == '0':
        abs_file_path = os.path.join(os.getcwd(),file_path) 
    else:
        abs_file_path = os.path.join(log_file_dir,file_path)
    # 打印日志
    current_app.logger.debug(f'abs file path is {abs_file_path}')
    filename=os.path.basename(abs_file_path)
    if os.path.exists(abs_file_path):
        filetype,islink=guess_type(abs_file_path)
        return send_file(abs_file_path, mimetype=filetype)
    else:
        return render_template('error_page_1.html', msg='File not exists!')

@repo_api.route('/receive_file/',methods=['POST'])
def receive_file():
    dir_path=request.args.get('path')
    # 去掉路径开头的/
    if dir_path and dir_path[0] == '/':
        dir_path=dir_path[1:]
    # 转换为绝对路径
    abs_save_path = os.path.join(os.getcwd(),dir_path)
    # 检查路径是否存在，不存在则返回错误信息
    if not os.path.exists(abs_save_path):
        current_app.logger.error(f"receive_file: {abs_save_path} not exists!")
        return jsonify({'code':1,'msg':'ERROR: Path not exists!'})
    # 接收文件
    if request.method == 'POST':
        # check if the post request has the file part
        if 'file' not in request.files:
            return jsonify({'code':1,'msg':'ERROR: Post request has no file part!'})
        file = request.files['file']
        # If the user does not select a file, the browser submits an
        # empty file without a filename.
        if file.filename == '':
            return jsonify({'code':2,'msg':'ERROR: Empty file without a filename!'})
        if file :
            #filename = secure_filename(file.filename)
            filename = file.filename
            # 检查文件名是否合法
            if not pathvalidate.is_valid_filename(filename):
                return jsonify({'code':3,'msg':'ERROR: Invalid file name:'+filename})
            # 保存文件
            try:
                file.save(os.path.join(abs_save_path, filename))
            # 捕获异常
            except  Exception as e:
                return jsonify({'code':4,'msg':'ERROR: Save file failed: '+filename+' '+str(e)})
            # 成功保存
            else:
                current_app.logger.info(f"receive_file: {filename} saved to {abs_save_path} successfully!")
                # 返回成功信息
                return jsonify({'code':0,'msg':'Upload Successfully: '+filename})

@repo_api.route('/download_file/')
def download_file():
    # request.args.get会自动解码url编码
    file_path=request.args.get('path','')
    is_logfile=request.args.get('is_logfile','0')

    # 去掉路径开头的/
    if file_path and file_path[0] == '/':
        file_path=file_path[1:] 
    if is_logfile == '0':
        abs_file_path=os.path.join(os.getcwd(),file_path)
    elif is_logfile == '1':
        abs_file_path=os.path.join(log_file_dir,file_path)

    filename=os.path.basename(abs_file_path)
    if os.path.exists(abs_file_path):
        return send_file(abs_file_path, as_attachment=True,download_name=urllib.parse.quote(filename, safe='/', encoding=None, errors=None))
    else:
        return render_template('error_page_1.html', msg='File not exists!')

@repo_api.route('/rename_file/')
def rename_file():
    dir_path=request.args.get('dir_path')
    # 去掉路径开头的/
    if dir_path and dir_path[0] == '/':
        dir_path=dir_path[1:]      
    old_name=request.args.get('file_name')
    new_name=request.args.get('new_name')
    old_file_path=os.path.join(dir_path,old_name)
    new_file_path=os.path.join(dir_path,new_name)
    if old_name == '':
        return jsonify({'code':1,'msg':'ERROR: Empty old file name!'})
    if new_name != '':
        # check if new_name is valid and not contain space
        if pathvalidate.is_valid_filename(new_name) and re.search(' ', new_name) == None:
            try:
                os.rename(old_file_path, new_file_path)
            except  Exception as e:
                return jsonify({'code':1,'msg':'ERROR: rename file failed! '+str(e)})
            else:
                return jsonify({'code':0,'msg':'Rename file successfully!'})  
        else:
            return jsonify({'code':2,'msg':'ERROR: Invalid new file name!'})  
    else:
        return jsonify({'code':3,'msg':'ERROR: Empty new file name!'})

@repo_api.route('/delete_file/')
def delete_file():
    dir_path=request.args.get('dir_path')
    # 去掉路径开头的/
    if dir_path and dir_path[0] == '/':
        dir_path=dir_path[1:]  
    file_name=request.args.get('file_name')
    file_path=os.path.join(dir_path,file_name)
    # 如果是链接文件
    if os.path.islink(file_path):
        try:    
            os.unlink(file_path)
        except  Exception as e:
            return jsonify({'code':1,'msg':'ERROR: Delete link file failed: '+file_name+' '+str(e)})
        else:
            return jsonify({'code':0,'msg':'Delete link file successfully: '+file_name})
    # 如果是普通文件
    elif os.path.isfile(file_path):
        if os.path.exists(file_path):
            try:    
                os.remove(file_path)
            except  Exception as e:
                return jsonify({'code':1,'msg':'ERROR: Delete file failed: '+file_name + ' ' +str(e)})
            else:
                return jsonify({'code':0,'msg':'Delete file successfully: '+file_name})
    # 如果是目录      
    elif os.path.isdir(file_path):
        if os.path.exists(file_path):
            try:    
                shutil.rmtree(file_path)
            except  Exception as e:
                return jsonify({'code':1,'msg':'ERROR: Delete directory failed: '+ file_name + ' ' +str(e)})
            else:
                return jsonify({'code':0,'msg':'Delete directory successfully: '+file_name})
    else:
        return jsonify({'code':2,'msg':'Unsupported file type:'+file_name})

# 压缩目录功能，通过调用系统7za命令实现
@repo_api.route('/compress_dir/')
def compress_dir():
    dir_path=request.args.get('dir_path')
    # 去掉路径开头的/
    if dir_path and dir_path[0] == '/':
        dir_path=dir_path[1:]   
    file_name=request.args.get('file_name')
    file_path=os.path.join(dir_path,file_name)
    if os.path.isdir(file_path):
        dir_zip_path=file_path+'.zip'
        p = subprocess.Popen(["7za","a", dir_zip_path, file_path],text=True,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            output, errs = p.communicate(timeout=3600)  # 压缩超时时间设为60分钟
        except subprocess.TimeoutExpired:
            p.kill()
            output, errs = p.communicate()
        returncode = p.poll()
        if returncode == 0:
            return jsonify({'code':returncode,'msg':output})
        else:
            return jsonify({'code':returncode,'msg':errs})
    else:
        return jsonify({'code':2,'msg':'ERROR: Not a directory!'})

# 解压缩文件功能，通过调用系统7za、tar命令实现
@repo_api.route('/decompress_file/')
def decompress_file():
    dir_path=request.args.get('dir_path')
    # 去掉路径开头的/
    if dir_path and dir_path[0] == '/':
        dir_path=dir_path[1:]
    # 如果dir_path为空，则表示当前为根路径
    if dir_path == '':
        dir_path="./"
    file_name=request.args.get('file_name')
    file_path=os.path.join(dir_path,file_name)
    # 获取文件后缀
    parse_path = pathlib.Path(file_path)
    file_suffixes = "".join(parse_path.suffixes)
    if file_suffixes == '.tar.gz':
        p = subprocess.Popen(["tar","xf", file_path, "-C",dir_path],text=True,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            output, errs = p.communicate(timeout=1800)  # 解压缩超时时间设为30分钟
        except subprocess.TimeoutExpired:
            p.kill()
            output, errs = p.communicate()
    else:
        p = subprocess.Popen(["7za","x", file_path, "-o"+dir_path, "-y"],text=True,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            output, errs = p.communicate(timeout=1800)  # 解压缩超时时间设为30分钟
        except subprocess.TimeoutExpired:
            p.kill()
            output, errs = p.communicate()
    returncode = p.poll()
    if returncode == 0:
        return jsonify({'code':returncode,'msg':output})
    else:
        return jsonify({'code':returncode,'msg':errs})

# 创建新目录功能
@repo_api.route('/new_dir/')
def new_dir():
    dir_path=request.args.get('dir_path')
    # 去掉路径开头的/
    if dir_path and dir_path[0] == '/':
        dir_path=dir_path[1:]
    new_dir_name=request.args.get('new_dir_name')
    if new_dir_name != '':
        # check if new_dir_name is valid and not contain space
        if pathvalidate.is_valid_filename(new_dir_name) and re.search(' ', new_dir_name) == None:
            if os.path.exists(os.path.join(dir_path,new_dir_name)):
                i=1
                new_dir_name_suffixed  = new_dir_name+'('+str(i)+ ')'
                while os.path.exists(os.path.join(dir_path,new_dir_name_suffixed)):
                    i=i+1
                    new_dir_name_suffixed =new_dir_name +'('+str(i)+ ')'
                new_dir_name = new_dir_name_suffixed
            try:
                os.mkdir(os.path.join(dir_path,new_dir_name))
            except  Exception as e:
                return jsonify({'code':1,'msg':'ERROR: Create new directory failed! '+str(e)})
            else:
                return jsonify({'code':0,'msg':'Success: Create new directory successfully: '+new_dir_name})  
        else:
            return jsonify({'code':2,'msg':'ERROR: Invalid new directory name: '+new_dir_name})  
    else:
        return jsonify({'code':3,'msg':'ERROR: Empty new directory name!'})
# 获取log日志文件列表
@repo_api.route('/log_file_list/',methods=['GET'])
def log_file_list():
    log_files_list = os.listdir(log_file_dir)
    log_file_info_list=[]
    count=0
    for log_file in log_files_list:
        abs_file_path = os.path.join(log_file_dir,log_file)
        st = os.lstat(abs_file_path)
        fsize = st.st_size
        fmtime = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(st.st_mtime))
        file_info_dict={
            "file_name": log_file, 
            "file_size": fsize,
            "file_mtime": fmtime
        }
        log_file_info_list.append(file_info_dict)
        count=count+1
    return  jsonify({'code':0,'msg':'yes','count':count,'data':log_file_info_list})      


# 读取repo_config_file配置文件，列出所有被管理的仓库   
@repo_api.route('/deb_repo_manage_list/',methods=['GET'])
def repo_manager_list():
    # 构建deb仓库信息列表
    deb_repo_info_list=[]
    # 读取RepoSyncInfo表的信息
    for deb_repo_info in repo_conf_info_db.query(DebRepoInfo).all():
        deb_repo_info_list.append(deb_repo_info.to_dict())
    return jsonify({'code':0,'msg':'yes','data':deb_repo_info_list})

# 新建deb仓库
@repo_api.route('/create_new_deb_repo/',methods=['POST'])
def create_new_deb_repo():
    #获取post请求参数
    post_data=request.json  #将json格式的请求数据转换为字典
    repopath=post_data['repopath']
    # 不允许直接使用/路径
    if repopath == '/':
        return jsonify({'code':1,'msg':'Cannot create repo with root path!'})
    # 去掉repopath开头的/
    if repopath and repopath[0] == '/':
        repopath=repopath[1:]
    # 检查repopath是否为合法路径
    if not pathvalidate.is_valid_filepath(repopath) or re.search(' ', repopath) != None:
        return jsonify({'code':2,'msg':'Invalid file path'}) 
    # 将repopath转换为绝对路径
    abs_path = os.path.join(os.getcwd(),repopath)
    # 查看abs_path是否已存在，存在则返回错误
    if os.path.exists(abs_path):
        return jsonify({'code':3,'msg':'Repo path already exists in file system!'})
    else:
        # 仓库conf目录路径
        conf_dir=os.path.join(abs_path,'conf')
        # 递归创建deb仓库目录及其conf目录，并设置权限，0o表示八进制
        try:
            os.makedirs(conf_dir, mode=0o755)
        except Exception as e:
            current_app.logger.error(f"Failed to create deb repo conf directory {conf_dir}, error message: {e}")
            return jsonify({'code':4,'msg':'Create deb repo conf directory failed!'})
        else:
            current_app.logger.info(f"Create deb repo conf directory successfully")
    # 构建distributions配置数据
    distributions_conf_data={
        'codename':post_data['dist_codename'],
        'update':post_data['dist_update'],
        'architectures':post_data['dist_architectures'],
        'components':post_data['dist_components'],
        'description':post_data['dist_description'] if post_data['dist_description'] else 'This is a repository create by repo manager.'
    }
    # 构建updates配置数据
    updates_conf_data={
        'name':post_data['update_name'],
        'suite':post_data['update_suite'],
        'architectures':post_data['update_architectures'],
        'components':post_data['update_components'],
        'method':post_data['update_method']
    }
    # 对输入配置参数进行校验
    # 如果update_name不为空，则对update相关必填参数进行校验，如果必填项为空，则返回错误信息
    if post_data['update_name']:
        if not post_data['update_suite'] or not post_data['update_architectures'] or not post_data['update_components'] or not post_data['update_method']:
            current_app.logger.error(f"Invalid update config data, update_name: {post_data['update_name']}, update_suite: {post_data['update_suite']}, update_architectures: {post_data['update_architectures']}, update_components: {post_data['update_components']}, update_method: {post_data['update_method']}")
            return jsonify({'code':6,'msg':'Invalid update config data!'})
        # 如果update相关参数校验通过，则生成updates配置文件
        elif render_tpl('deb-repo','updates.j2',os.path.join(conf_dir,'updates'),updates_conf_data):
            current_app.logger.info(f"Create deb repo conf file successfully")
        else:
            current_app.logger.error(f"Failed to create deb conf file")
            return jsonify({'code':7,'msg':'Create deb repo conf file failed!'})
    # 如果update_name为空，则不生成updates配置文件
    # 通过模板渲染生成distributions配置文件
    # 通过jinjia2模板生成distributions配置文件
    if render_tpl('deb-repo','distributions.j2',os.path.join(conf_dir,'distributions'),distributions_conf_data):
        current_app.logger.info(f"Create deb repo conf file successfully")
        # 将创建的仓库信息写入到被管理的数据库deb_repo_info表中
        result=add_new_deb_repo(repopath)
        return jsonify({'code':0,'msg':'Create new deb repo successfully!'})
    else:
        current_app.logger.error(f"Failed to create deb conf file")
        return jsonify({'code':5,'msg':'Create deb repo conf file failed!'})

# 添加已有的deb仓库，写入到repo_conf_info_db数据库中的deb_repo_info表中
@repo_api.route('/add_deb_repo_manage/',methods=['GET'])
def add_deb_repo_manage():
    # 获取get请求参数
    repopath=request.args.get('repopath')
    # 调用add_new_deb_repo函数，将仓库信息写入到数据库中
    result=add_new_deb_repo(repopath)
    return jsonify({'code':result[0],'msg':result[1]})
    
# 删除被管理的仓库
@repo_api.route('/delete_deb_repo_manage/',methods=['GET']) 
def delete_deb_repo_manage():
    # 获取get请求参数
    id=request.args.get('id')
    # 删除repo_conf_info_db数据库中的deb_repo_info表中的指定仓库信息
    repo_conf_info_db.query(DebRepoInfo).filter(DebRepoInfo.id == int(id)).delete()
    # 将修改提交至数据库
    try:
        repo_conf_info_db.commit()
    except Exception as e:
        current_app.logger.error(f'Failed to delete repo conf id:{id} from deb repo info db! {str(e)}')
        return jsonify({'code':1,'msg':'Failed to delete repo from database!'+str(e)})
    else:
        current_app.logger.info(f'Success in deleting repo conf id:{id} from deb repo info db')
        return jsonify({'code':0,'msg':'Success in deleting repo from deb repo info db'})

# 刷新指定的仓库信息
@repo_api.route('/refresh_deb_repo_manage/',methods=['GET'])
def refresh_deb_repo_manage():
    id=request.args.get('id')
    repopath=request.args.get('repopath')
    codename=request.args.get('codename')

    # 去掉repopath开头的/
    if repopath and repopath[0] == '/':
        repopath_no_rootpath=repopath[1:]
    else:
        repopath_no_rootpath=repopath
    # 将repopath转换为绝对路径
    abs_repo_dir_path = os.path.join(os.getcwd(),repopath_no_rootpath)

    # 执行reprepro sizes 查看仓库信息，获取对应codename的size信息
    p = subprocess.Popen(["reprepro", "sizes",codename],cwd=abs_repo_dir_path,text=True,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        output, errs = p.communicate(timeout=60)  # 仓库信息超时时间设置为1分钟
    except subprocess.TimeoutExpired:
        p.kill()
        output, errs = p.communicate()
    returncode = p.poll()   
    if returncode == 0:
        # 去掉第一行头信息，取出的仓库codename+size信息列表
        distribution_info_list=output.splitlines()[1:]
        for distribution_info in distribution_info_list:
            info_list=re.split(r'\s+',distribution_info)
            if info_list[0] == codename:
                size=info_list[1]
                # 因为codename唯一,匹配到即退出
                break
    else:
        return jsonify({'code':returncode,'msg':'<p>Failed to get repo size by reprepro command!</p>'+errs})  #如果reprepro sizes命令失败，则返回命令错误信息

    # 读取仓库distributions文件中的component信息、architectures信息
    repo_conf_dist_file=os.path.join(abs_repo_dir_path,"./conf/distributions")
    with open(repo_conf_dist_file, 'r', encoding='utf-8') as file_r:
        dist_conf_str = file_r.read()
        # 用单独的空行分割配置文件，然后再用正则表达式匹配出对应codename的component信息和architectures信息
        conf_list=re.split(r'\n\n',dist_conf_str)
        for conf_item in conf_list:
            components_match=re.findall(r'Codename: '+ codename +r'.*Components: ([^\n]+)',conf_item,re.DOTALL|re.IGNORECASE)
            architectures_match=re.findall(r'Codename: '+ codename +r'.*Architectures: ([^\n]+)',conf_item,re.DOTALL|re.IGNORECASE)
            #找到第一个匹配即跳出循环，因为codename唯一
            if components_match != []:
                break
    # 从数据库中找到指定仓库信息，修改相关信息
    deb_repo_info=repo_conf_info_db.query(DebRepoInfo).filter(DebRepoInfo.id == int(id)).first()
    if deb_repo_info == None:
        return jsonify({'code':3,'msg':f'Failed to find repo info with id:{id} in database!'})
    else:
        deb_repo_info.components=components_match[0].strip()
        deb_repo_info.architectures=architectures_match[0].strip()
        deb_repo_info.size=int(size)
    # 将修改提交至数据库
    try:
        repo_conf_info_db.commit()
    except Exception as e:
        current_app.logger.error(f'Failed to refresh repo id:{id} repopath:{repopath} codename:{codename} info in deb repo info db! {str(e)}')
        return jsonify({'code':4,'msg':'Failed to refresh repo!'+str(e)})
    else:
        current_app.logger.info(f'Success in refreshing repo id:{id} repopath:{repopath} codename:{codename} info in deb repo info db')
        return jsonify({'code':0,'msg':'Success in refreshing repo info in deb repo info db'})

# 修改仓库update中的Method配置

# 获取仓库update信息
@repo_api.route('/get_deb_repo_update_info/')
def get_deb_repo_update_info():
    repopath=request.args.get('repopath')
    codename=request.args.get('codename')
    # 将repopath转换为绝对路径
    if repopath and repopath[0] == '/':
        repopath_no_rootpath=repopath[1:]
    else:
        repopath_no_rootpath=repopath
    abs_repo_dir_path = os.path.join(os.getcwd(),repopath_no_rootpath) 
    # distributions文件路径，此处无需检查路径是否存在，因为已经在前面检查过了
    repo_conf_dist_file=os.path.join(abs_repo_dir_path,"./conf/distributions")
    # updates配置文件路径
    repo_conf_updates_file=os.path.join(abs_repo_dir_path,"./conf/updates")
    # 检查updates文件是否存在
    if not os.path.exists(repo_conf_updates_file):
        return jsonify({'code':1,'msg':'Repo conf updates file not exists!'})
    # 读取distributions文件中的codename对应的update列表
    with open(repo_conf_dist_file, 'r', encoding='utf-8') as file_r:
        dist_conf_str = file_r.read()
        # 用单独的空行分割配置文件，然后再用正则表达式匹配出codename对应的update列表
        conf_list=re.split(r'\n\n',dist_conf_str)
        for conf_item in conf_list:
            update_match=re.findall(r'Codename: '+ codename +r'.*Update: ([^\n]+)',conf_item,re.DOTALL|re.IGNORECASE)
            #找到第一个匹配即跳出循环，因为codename唯一
            if update_match != []:
                break
    if update_match == []:
        return jsonify({'code':2,'msg':'Failed to get update config from repo conf distributions file!'})
    else:
        update_name = update_match[0].strip()
    # 读取updates文件中的update列表
    with open(repo_conf_updates_file, 'r', encoding='utf-8') as file_r:
        updates_conf_str = file_r.read()
        # 用单独的空行分割配置文件，然后再用正则表达式匹配出update列表
        conf_list=re.split(r'\n\n',updates_conf_str)
        for conf_item in conf_list:
            method_match=re.findall(r'Name: '+ update_name +r'.*Method: ([^\n]+)',conf_item,re.DOTALL|re.IGNORECASE)
            #找到第一个匹配即跳出循环，因为codename唯一
            if method_match != []:
                break
    if method_match == []:
        return jsonify({'code':2,'msg':'Failed to get update info from repo conf updates file!'})
    else:
        return jsonify({'code':0,'msg':'Success','data':method_match[0].strip()})

# 修改仓库update信息
@repo_api.route('/edit_deb_repo_update_conf/',methods=['GET'])
def modify_repo_update_info():
    abs_path=request.args.get('abs_path')
    codename=request.args.get('codename')
    update_method=request.args.get('update_method')
    # 获取abs_path路径下codename对应的update配置名
    repo_conf_dist_file=os.path.join(abs_path,"./conf/distributions")
    with open(repo_conf_dist_file, 'r', encoding='utf-8') as file_r:
        dist_conf_str = file_r.read()
        # 用单独的空行分割配置文件，然后再用正则表达式匹配出codename对应的update配置名
        conf_list=re.split(r'\n\n',dist_conf_str)
        for conf_item in conf_list:
            update_match=re.findall(r'Codename: '+ codename +r'.*Update: ([^\n]+)',conf_item,re.DOTALL|re.IGNORECASE)
            #找到第一个匹配即跳出循环，因为codename唯一
            if update_match != []:
                break
    if update_match == []:
        return jsonify({'code':1,'msg':'Failed to get update config from repo conf distributions file!'})
    else:
        update_name = update_match[0].strip()
    # 读取update文件，读取内容
    repo_conf_updates_file=os.path.join(abs_path,"./conf/updates")
    with open(repo_conf_updates_file, 'r', encoding='utf-8') as file_r:
        updates_conf_str = file_r.read()
        # 修改找到update配置文件中的对应update名称的Method配置项进行修改        
        pattern = re.compile(r'(Name: '+update_name+r'.*?Method: )\S+',re.DOTALL)   #re.DOTALL 表示让.可以匹配换行符\n
        modified_updates_conf_str=pattern.sub(r'\1'+update_method,updates_conf_str)
    # 写入修改后的update配置文件
    try:
        with open(repo_conf_updates_file, 'w', encoding='utf-8') as file_w:
            file_w.write(modified_updates_conf_str)
    except Exception as e:
        return jsonify({'code':2,'msg':'Failed to modify repo updates conf file!'+str(e)})
    else:
        return jsonify({'code':0,'msg':'Success in modifying repo updates conf file!'})

# 从上游仓库update功能
@repo_api.route('/deb_repo_update/')
def deb_repo_update_api():
    repopath=request.args.get('repopath')
    codename=request.args.get('codename')

    update_result = deb_repo_update(repopath,codename)
    if update_result[0] == 0:
        # 在sync_obj_info表中搜索该仓库
        syncobj=repo_sync_info_db.query(SyncObjInfo).filter(and_(SyncObjInfo.repopath == repopath,SyncObjInfo.codename == codename)).first()
        # 如果syncobj不为空，且origin为self_id，则更新其sn号（如果origin为self_id，则说明该仓库是自己创建的，需要更新其sn号）
        if syncobj and syncobj.origin == get_self_id():
            syncobj.update_sn()
        current_app.logger.info(f'reprepro update successfully')
        return jsonify({'code':update_result[0],'msg':'<p>Success in updating deb repo</p>'})
    else:
        current_app.logger.info(f'reprepro update failed')
        return jsonify({'code':update_result[0],'msg':f"<p>Failed to update deb repo!{update_result[1]}</p>"})
      
# 获取仓库component列表
@repo_api.route('/get_repo_component_list/')
def get_repo_component_list():
    repopath=request.args.get('repopath')
    codename=request.args.get('codename')
    # 将repopath转换为绝对路径
    if repopath and repopath[0] == '/':
        repopath_no_rootpath=repopath[1:]
    else:
        repopath_no_rootpath=repopath
    abs_repo_dir_path = os.path.join(os.getcwd(),repopath_no_rootpath) 
    # 检查abs_repo_dir_path是否存在
    if not os.path.exists(abs_repo_dir_path):
        current_app.logger.error(f'Failed to get repo component list, repo path not exists! repopath:{repopath} codename:{codename}')
        return jsonify({'code':1,'msg':'Repo path not exists!'})
    # distributions文件路径
    repo_conf_dist_file=os.path.join(abs_repo_dir_path,"./conf/distributions")
    # 检查distributions文件是否存在
    if not os.path.exists(repo_conf_dist_file):
        current_app.logger.error(f'Failed to get repo component list, repo conf distributions file not exists! repopath:{repopath} codename:{codename}')
        return jsonify({'code':1,'msg':'Repo conf distributions file not exists!'})
    # 读取distributions文件中的component列表
    with open(repo_conf_dist_file, 'r', encoding='utf-8') as file_r:
        dist_conf_str = file_r.read()
        # 用单独的空行分割配置文件，然后再用正则表达式匹配出component列表
        conf_list=re.split(r'\n\n',dist_conf_str)
        for conf_item in conf_list:
            components_match=re.findall(r'Codename: '+ codename +r'.*Components: ([^\n]+)',conf_item,re.DOTALL|re.IGNORECASE)
            #找到第一个匹配即跳出循环，因为codename唯一
            if components_match != []:
                break

    if components_match == []:
        return jsonify({'code':2,'msg':'Failed to get component list from repo conf distributions file!'})
    else:
        # 将components_match[0]按空格分割成component列表
        component_list=re.split(r'\s+',components_match[0])
        return jsonify({'code':0,'msg':'Success','data':component_list})

# 搜索仓库中的包
@repo_api.route('/repo_pkg_search/')
def repo_pkg_search():
    repopath=request.args.get('repopath')
    codename=request.args.get('codename')
    pkg_name_pattern=request.args.get('pkg_name_pattern')
    # 去掉repopath开头的/
    if repopath and repopath[0] == '/':
        repopath_no_rootpath=repopath[1:]
    else:
        repopath_no_rootpath=repopath
    # 将repopath转换为绝对路径
    abs_repo_dir_path = os.path.join(os.getcwd(),repopath_no_rootpath) 
    # 检查repopath是否存在
    if not os.path.exists(abs_repo_dir_path):
        return jsonify({'code':1,'msg':'Repo path not exists!'})
    # 检查repo_lockfile是否存在，如果存在，则等待1秒后再次检查
    repo_lockfile_path=os.path.join(abs_repo_dir_path,"./db/lockfile")
    n=0
    while os.path.exists(repo_lockfile_path):
        time.sleep(1)
        n=n+1
        # 超时时间设为10秒
        if n>10:
            return jsonify({'code':2,'msg':'Repo lockfile exists, please try again later!'})
    if pkg_name_pattern == '':
        pkg_name_pattern='*'
    pkg_name_condition='Package (%'+pkg_name_pattern+')'
    # 执行reprepro listfilter命令搜索包
    p = subprocess.Popen(["reprepro", "listfilter", codename, pkg_name_condition],cwd=abs_repo_dir_path,text=True,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        output, errs = p.communicate(timeout=120)  # 包搜索超时时间设置为2分钟
    except subprocess.TimeoutExpired:
        p.kill()
        output, errs = p.communicate()
    returncode = p.poll()
    if returncode == 0:
        repo_pkg_search_info_list=[]
        count=0
        for pkginfo in output.splitlines():
            pkg_repo_info = pkginfo.split(": ")[0]
            codename=pkg_repo_info.split('|')[0]
            component=pkg_repo_info.split('|')[1]
            arch=pkg_repo_info.split('|')[2]
            pkg_name_ver = pkginfo.split(": ")[1]
            pkg_name=pkg_name_ver.split(' ')[0]
            pkg_ver=pkg_name_ver.split(' ')[1]
            pkg_info_dict={
                'codename': codename,
                'component': component,
                'arch': arch,
                'pkg_name': pkg_name,
                'pkg_ver': urllib.parse.quote(pkg_ver)
            }
            repo_pkg_search_info_list.append(pkg_info_dict)
            count=count+1
        return jsonify({'code':returncode,'msg':'success','count':count,'data':repo_pkg_search_info_list})
    else:
        return jsonify({'code':returncode,'msg':errs})

# 删除仓库中的包
@repo_api.route('/del_pkg_from_repo/')
def del_pkg_from_repo():
    repopath=request.args.get('repopath')
    codename=request.args.get('codename')
    component=request.args.get('component')
    arch=request.args.get('arch')
    pkg_name=request.args.get('pkg_name')
    # 将repopath转换为绝对路径
    if repopath and repopath[0] == '/':
        repopath_no_rootpath=repopath[1:]
    else:
        repopath_no_rootpath=repopath
    abs_repo_dir_path = os.path.join(os.getcwd(),repopath_no_rootpath) 
    # 检查abs_repo_dir_path是否存在
    if not os.path.exists(abs_repo_dir_path):
        return jsonify({'code':1,'msg':'Repo path not exists!'})
    # 检查repo_lockfile是否存在，如果存在，则等待1秒后再次检查
    repo_lockfile_path=os.path.join(abs_repo_dir_path,"./db/lockfile")
    n=0
    while os.path.exists(repo_lockfile_path):
        print("repo_lockfile_path exists, wait 1 second")
        time.sleep(1)
        n=n+1
        # 超时时间设为10秒
        if n>10:
            return jsonify({'code':2,'msg':'Repo lockfile exists, please try again later!'})
    # 检查pkg_name是否为空
    if pkg_name == '':
        return jsonify({'code':2,'msg':'Empty package name!'})
    # 执行删除操作
    p=subprocess.Popen(["reprepro", "-b", abs_repo_dir_path, "-C",component,"-A",arch,"remove",codename,pkg_name],text=True,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        output, errs = p.communicate(timeout=120)  # 包删除超时时间设置为2分钟
    except subprocess.TimeoutExpired:
        p.kill()
        output, errs = p.communicate()  
    returncode = p.poll()
    if returncode == 0:
        # 打印删除成功日志
        current_app.logger.info(f'Package {pkg_name} deleted from repo {repopath_no_rootpath} {codename} successfully!')
        # 成功删除，在sync_obj_info表中搜索该仓库
        syncobj=repo_sync_info_db.query(SyncObjInfo).filter_by(objtype='deb-repo',rela_path=repopath_no_rootpath,codename=codename).first()
        # 如果syncobj不为空，则更新其sn号
        if syncobj:
            syncobj.update_sn()
            # 将该syncobj 的同步状态全部置为未同步
            pshared_db.query(NodeSyncObjStatus).filter_by(objtype='deb-repo',rela_path=syncobj.rela_path,codename=syncobj.codename).update({'status':False})
            # 将修改提交至数据库
            try:
                repo_sync_info_db.commit()
                pshared_db.commit()
            except Exception as e:
                repo_sync_info_db.rollback()
                current_app.logger.error(f'Failed to update Syncobj deb-repo: {repopath_no_rootpath} {codename} sn number or NodeSyncObjStatus!ERROR:{str(e)}')
                return jsonify({'code':1,'msg':f'Failed to update syncobj sn number or NodeSyncObjStatus!ERROR:{str(e)}'})
            else:
                current_app.logger.info(f'Syncobj deb-repo: {repopath_no_rootpath} {codename} sn number updated successfully!')
        return jsonify({'code':returncode,'msg':'<p>Success in deleting package!</p>'+output})
    else:
        # 打印删除失败日志
        current_app.logger.error(f'Failed to delete package {pkg_name} from repo {repopath_no_rootpath} {codename}! ERROR:{errs}')
        return jsonify({'code':returncode,'msg':'<p>Failed to delete package!</p>'+errs})

# 将仓库路径下的deb包导入到仓库中
@repo_api.route('/import_deb_pkg_to_repo/')
def import_deb_pkg_to_repo():
    repopath=request.args.get('repopath')
    codename=request.args.get('codename')
    component=request.args.get('component')

    # 将repopath转换为绝对路径
    if repopath and repopath[0] == '/':
        repopath_no_rootpath=repopath[1:]
    else:
        repopath_no_rootpath=repopath
    abs_repo_dir_path = os.path.join(os.getcwd(),repopath_no_rootpath) 
    # 检查repopath是否存在
    if not os.path.exists(abs_repo_dir_path):
        return jsonify({'code':1,'msg':'Repo path not exists!'})
    # 检查repo_lockfile是否存在，如果存在，则等待1秒后再次检查
    repo_lockfile_path=os.path.join(abs_repo_dir_path,"./db/lockfile")
    n=0
    while os.path.exists(repo_lockfile_path):
        print("repo_lockfile_path exists, wait 1 second")
        time.sleep(1)
        n=n+1
        # 超时时间设为10秒
        if n>10:
            return jsonify({'code':2,'msg':'Repo lockfile exists, please try again later!'})
    # 判断trash目录是否存在，如果不存在则创建
    trash_dir_path=os.path.join(abs_repo_dir_path,"trash")
    if not os.path.exists(trash_dir_path):
        os.mkdir(trash_dir_path)
    # 判断trash目录是否为空，不为空则删除其中所有文件
    if os.listdir(trash_dir_path):
        for file in os.listdir(trash_dir_path):
            os.remove(os.path.join(trash_dir_path,file))
    # 获取当前目录下的deb包列表
    file_list = os.listdir(abs_repo_dir_path)
    # 判断当前文件是否为deb后缀的文件
    def is_deb_file(file_name):
        if re.match(r'.*\.deb$', file_name,re.IGNORECASE):
            return True
        else:
            return False
    # deb文件列表
    deb_file_list = [ file for file in file_list if is_deb_file(file) ]
    # 错误信息列表
    error_list=[]
    # 失败导入的包列表
    fail_import_list=[]
    # 成功导入的包列表
    success_import_list=[]
    # 遍历deb文件列表，逐个文件导入仓库
    for i in range(len(deb_file_list)):
        # 检查repo_lockfile是否存在，如果存在，则等待1秒后再次检查
        n=0
        while os.path.exists(repo_lockfile_path):
            print("repo_lockfile_path exists, wait 1 second")
            time.sleep(1)
            n=n+1
            # 超时时间设为10秒
            if n>10:
                return jsonify({'code':2,'msg':'Repo lockfile exists, please try later!'})
        # 执行导入操作
        # 如果component为空，则执行不带-C参数的includedeb命令
        if component == '':
            p=subprocess.Popen(["reprepro","includedeb",codename,deb_file_list[i]],cwd=abs_repo_dir_path,text=True,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        else:
            p=subprocess.Popen(["reprepro","-C",component,"includedeb",codename,deb_file_list[i]],cwd=abs_repo_dir_path,text=True,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            output, errs = p.communicate(timeout=60)  # 单个包导入超时时间设置为1分钟 
        except subprocess.TimeoutExpired:
            p.kill()
            output, errs = p.communicate()  
        returncode = p.poll()
        # 成功导入
        if returncode == 0:
            # 从列表删除，并将该包名加入success_import_list
            success_import_list.append(deb_file_list[i])
            # 导入成功，将文件删除
            os.remove(os.path.join(abs_repo_dir_path,deb_file_list[i]))
        # 由于deb包没有申明section导致的报错
        elif returncode == 255:
            # 如果是255报错，说明是该deb包control文件没有申明section或priority，则执行带-S util（默认导入util section），-P optional（默认priority为optional）的includedeb命令
            # 如果component为空，则执行不带-C参数的includedeb命令
            if component == '':
                p=subprocess.Popen(["reprepro","-S","util","-P","optional","includedeb",codename,deb_file_list[i]],cwd=abs_repo_dir_path,text=True,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            else:
                p=subprocess.Popen(["reprepro","-S","util","-P","optional","-C",component,"includedeb",codename,deb_file_list[i]],cwd=abs_repo_dir_path,text=True,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                output, errs = p.communicate(timeout=60)  # 单个包导入超时时间设置为1分钟 
            except subprocess.TimeoutExpired:
                p.kill()
                output, errs = p.communicate()  
            returncode = p.poll()
            # 如果成功导入
            if returncode == 0:
                # 从列表删除，并将该包名加入success_import_list
                success_import_list.append(deb_file_list[i])
                # 导入成功，将文件删除
                os.remove(os.path.join(abs_repo_dir_path,deb_file_list[i]))
            # 依然导入失败，则记录失败信息
            else:
                # 记录导入失败的包名列表
                fail_import_list.append(deb_file_list[i])
                # 导入失败，将deb文件移动到trash目录
                shutil.move(os.path.join(abs_repo_dir_path,deb_file_list[i]), os.path.join(trash_dir_path,deb_file_list[i]));
                error_list.append(errs)
        # 其他报错
        else:
            # 记录导入失败的包名列表
            fail_import_list.append(deb_file_list[i])
            # 导入失败，将deb文件移动到trash目录
            shutil.move(os.path.join(abs_repo_dir_path,deb_file_list[i]), os.path.join(trash_dir_path,deb_file_list[i]));
            error_list.append(errs)
    # 如果有导入成功的包，则更新syncobj的sn号
    if len(success_import_list) > 0:
        # 打印导入成功日志
        current_app.logger.info(f'Packages {success_import_list} imported to repo {repopath_no_rootpath} {codename} successfully!')
        # 在sync_obj_info表中搜索该仓库
        syncobj=repo_sync_info_db.query(SyncObjInfo).filter_by(objtype='deb-repo',rela_path = repopath_no_rootpath,codename = codename).first()
        # 如果syncobj不为空，则更新其sn号
        if syncobj:
            syncobj.update_sn()
            # 将该syncobj 的同步状态全部置为未同步
            pshared_db.query(NodeSyncObjStatus).filter_by(objtype='deb-repo',rela_path=syncobj.rela_path,codename=syncobj.codename).update({'status':False})
            # 将修改提交至数据库
            try:
                pshared_db.commit()
                repo_sync_info_db.commit()
            except Exception as e:
                repo_sync_info_db.rollback()
                current_app.logger.error(f'Failed to update Syncobj deb-repo: {repopath_no_rootpath} {codename} sn number or NodeSyncObjStatus!ERROR:{str(e)}')
                # 未成功更新sn号，则返回错误信息至前端
                return jsonify({'code':1,'msg':f'Failed to update sn number or NodeSyncObjStatus!ERROR:{str(e)}'})
            else:
                current_app.logger.info(f"Syncobj deb-repo: {repopath_no_rootpath} {codename} sn number updated successfully!")
    # 生成错误deb对应err信息
    err_message_list=[ fail_import_list[i]+': '+error_list[i] for i in range(len(error_list)) ]
    if len(fail_import_list) == 0:
        return jsonify({'code':0,'msg':'<p>Success in importing packages!</p><p>Packages :</p> Count:'+str(len(success_import_list))})
    else:
        # 打印导入失败日志
        current_app.logger.error(f'Failed to import packages {fail_import_list} to repo {repopath_no_rootpath} {codename}! ERROR:{err_message_list}')
        return jsonify({'code':1,'msg':'<p>Failed to import packages!</p><p>Error message: </p> '+'<br>'.join(err_message_list)})



