from sqlalchemy import create_engine,text
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker,declarative_base, Mapped, mapped_column
import os

# 获取数据库目录绝对路径
current_dir = os.path.dirname(os.path.abspath(__file__))
database_dir = os.path.join(current_dir,"databases")
share_memory_dir = '/dev/shm'
# 定义数据库路径（不存在会自动创建）
uos_api_SQLiteURL = 'sqlite:///'+ os.path.join(database_dir,'uos_api.db')
# 定义终端任务信息收集数据库
task_info_SQLiteURL = 'sqlite:///'+ os.path.join(database_dir,'task_info.db')
# 定义repo_sync_info数据库链接
repo_sync_info_SQLiteURL = 'sqlite:///'+ os.path.join(database_dir,'repo_sync_info.db')
# 定义共享数据库链接
pshared_db_SQLiteURL = 'sqlite:///' + os.path.join(share_memory_dir,'pshared_db.db')
# 定义仓库配置信息数据库连接
repo_conf_info_SQLiteURL='sqlite:///'+ os.path.join(database_dir,'repo_conf_info.db')
# 定义仓库update信息数据库连接
repo_update_info_SQLiteURL='sqlite:///'+ os.path.join(database_dir,'repo_update_info.db')

# 创建engine，uos_api数据库驱动信息
uos_api_engine = create_engine(
    url=uos_api_SQLiteURL,
    echo=False,    # 是否打开sqlalchemy ORM过程中的详细信息
    connect_args={
        'check_same_thread':False   # 是否多线程,False表示支持多线程
    }
)
# 创建engine，task_info数据库驱动信息
task_info_engine = create_engine(
    url=task_info_SQLiteURL,
    echo=False,    # 是否打开sqlalchemy ORM过程中的详细信息
    connect_args={
        'check_same_thread':False   # 是否多线程
    }
)
# 创建engine，repo_sync_info数据驱动信息
repo_sync_info_engine = create_engine(
    url=repo_sync_info_SQLiteURL,
    echo=False,    # 是否打开sqlalchemy ORM过程中的详细信息
    connect_args={
        'check_same_thread':False   # 是否多线程
    }
)

# 创建内存数据库pshared驱动信息
pshared_db_engine = create_engine(
    url=pshared_db_SQLiteURL,
    echo=False,    # 是否打开sqlalchemy ORM过程中的详细信息
    connect_args={
        'check_same_thread':False  # 是否多线程
    },
    poolclass=StaticPool,
)

# 创建engine,repo_conf_info 数据库驱动信息
repo_conf_info_engine = create_engine(
    url=repo_conf_info_SQLiteURL,
    echo=False,    # 是否打开sqlalchemy ORM过程中的详细信息
    connect_args={
        'check_same_thread':False   # 是否多线程
    }
)

# 创建engine,repo_update_info 数据库驱动信息
repo_update_info_engine = create_engine(
    url=repo_update_info_SQLiteURL,
    echo=False,    # 是否打开sqlalchemy ORM过程中的详细信息
    connect_args={
        'check_same_thread':False   # 是否多线程
    }
)

# 连接到数据库,设置数据库参数
with pshared_db_engine.connect() as connection:
    # 设置journal_mode为WAL
    connection.execute(text('PRAGMA journal_mode=WAL'))
    # cache_size：设置缓存大小，负数值：表示以KB为单位的内存大小，这里设置为10MB 
    connection.execute(text('PRAGMA cache_size=-10240'))    
    # 设置同步模式为OFF
    connection.execute(text('PRAGMA synchronous=NORMAL'))
    # 设置WAL自动检查点间隔
    connection.execute(text('PRAGMA wal_autocheckpoint=5000'))


# 创建session类对象（建立和数据库的链接）
uos_api_session = sessionmaker(
    bind=uos_api_engine,
    autoflush=False,
    autocommit=False
)
# 创建session类对象（建立和数据库的链接）
task_info_session = sessionmaker(
    bind=task_info_engine,
    autoflush=False,
    autocommit=False
)
# 创建repo_sync_info的session类对象（建立和数据库的链接）
repo_sync_info_session = sessionmaker(
    bind=repo_sync_info_engine,
    autoflush=False,
    autocommit=False
)
# 创建pshared_db数据库session类对象
pshared_db_session = sessionmaker(
    bind=pshared_db_engine,
    autoflush=False,
    autocommit=False
)
# 创建repo_conf_info的session类对象（建立和数据库的链接）
repo_conf_info_session = sessionmaker(
    bind=repo_conf_info_engine,
    autoflush=False,
    autocommit=False
)
# 创建repo_update_info的session类对象（建立和数据库的链接）
repo_update_info_session = sessionmaker(
    bind=repo_update_info_engine,
    autoflush=False,
    autocommit=False
)


# 创建uos_api_session实例（实例化）
uos_api_db = uos_api_session()
# 创建task_info_session实例（实例化）
task_info_db = task_info_session()
# 创建repo_sync_info_session实例（实例化）  
repo_sync_info_db = repo_sync_info_session()
# 创建pshared_db_session实例（实例化）
pshared_db = pshared_db_session()
# 创建repo_conf_info_session实例（实例化）
repo_conf_info_db = repo_conf_info_session()
# 创建repo_update_info_session实例（实例化）
repo_update_info_db = repo_update_info_session()

# 数据表的基类（定义表结构用）
uos_api_Base = declarative_base()
task_info_Base = declarative_base()
repo_sync_info_Base = declarative_base()
pshared_db_Base = declarative_base()
repo_conf_info_Base = declarative_base()
repo_update_info_Base = declarative_base()



# 初始化数据库
if __name__ == '__main__':
    uos_api_Base.metadata.create_all(uos_api_engine)
    task_info_Base.metadata.create_all(task_info_engine)
    repo_sync_info_Base.metadata.create_all(repo_sync_info_engine)
    pshared_db_Base.metadata.create_all(pshared_db_engine)
    repo_conf_info_Base.metadata.create_all(repo_conf_info_engine)
    repo_update_info_Base.metadata.create_all(repo_update_info_engine)


