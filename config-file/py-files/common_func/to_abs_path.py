import os
# 定义函数：将前端传递过来的相对路径转换为绝对路径
def to_abs_path(path:str)->str:
    # 去掉路径开头的/
    if path and path[0] == '/':
        rela_path=path[1:]
    # 如果不是以/开头，则可以直接使用
    else: 
        rela_path=path
    abs_path=os.path.normpath(os.path.join(os.getcwd(),rela_path))
    return abs_path