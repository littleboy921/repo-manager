#!/bin/bash
# author: zhangchiqian
# date: 2025-0114
# version: 0.1
# description: Use git command to manage a git repo,and add all files in current directory to the repo.


case $1 in
    init)
        # create a new repo
        # 查看当前目录下是否存在.git文件夹，如果存在，则说明已经存在一个仓库，不再创建
        if [ -d ".git" ]; then
            echo "This directory is already a git repository."
        else
            git init
        fi

        # add all files in current directory to the repo
        git add .

        # commit all changes
        git commit -m "$(date +%F-%H-%M-%S):git initial commit"
    ;;
    commit)
        # add and commit all changes
        git add .
        git commit -m "$(date +%F-%H-%M-%S):git commit"
    ;;
    pull)
        # check if dir is exist
        # pull all changes from remote repo
        git pull
    ;;
    *)
        echo "Usage: $0 {init|commit|pull}"
    ;;
esac
