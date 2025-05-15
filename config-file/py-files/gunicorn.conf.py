import multiprocessing

bind = '127.0.0.1:5000'  # 绑定的IP地址和端口
workers = multiprocessing.cpu_count() * 2 + 1  # 工作进程数
chdir = '../../data-file/'
errorlog = '../config-file/logs/error.log'  # 错误日志文件的路径
accesslog = '../config-file/logs/access.log'  # 访问日志文件的路径
loglevel = 'debug'  # 日志级别