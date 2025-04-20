# PixivCrawl

[直连版入口](https://github.com/kanostars/PixivCrawl/tree/vpn)

旨在通过UID或者链接地址(画师或者插画的都行)下载对应的插画作品。

通过应用登录可以下载更多图片。

程序是先获取所以图片的大小信息，然后再将所有信息放入下载队列进行下载。如果其中有动图的话，会在最后拼接成gif。

项目运行后会自动生成一个log文件夹存放日志信息，
下载图片后会自动生成相应的文件夹存放图片：

- artworks_IMG
    - 图片id
      -存放的图片
      ...
- workers_IMG
    - 画师id
        - 存放的图片
          ...
- pixivCrawl.json

（可选）js文件需要搭配浏览器插件（篡改猴测试版）使用

# 使用说明
**在使用此应用之前，请先打开你的梯子软件**
## 1. 直接运行exe文件
点击exe文件，默认是以管理员方式打开。

## 2. 使用带参数的命令运行
```
# example by 画师ID
pixivCrawl.exe -w "755446" -cookie " " -sn -ef  
```
```
# example by 作品ID
pixivCrawl.exe -a "129270666" -cookie " " -sn -ef  
```
必填项部分：
- `-w` | `--workerID` 画师ID
- `-a` | `--artworkID`  作品ID

**注意-w 和 -a 只能二选一**

可选项部分：
- `-cookie` | `--cookie` 登录cookie
- `-sn` | start_now 是否立刻下载
- `-ef` | exist_finish 下载结束后是否自动退出


## ~~3. 使用浏览器插件运行(已废除)~~

这一点是第二点的延伸，原理一样。

以下是使用教程：

1. 安装 **Tampermonkey测试版** 插件，注意一定是**测试版
   **：https://chrome.google.com/webstore/detail/gcalenpjmijncebpfijmoaglllgpjagf
2. 安装 **脚本文件**： https://greasyfork.org/zh-CN/scripts/533224-pixiv-download
3. 在扩展中启用脚本插件。
4. 在浏览器中打开pixiv网站，当网址url为：https://www.pixiv.net/artworks/*或者https://www.pixiv.net/users/* 时， 即进入到插画页面或者画师空间时，
    脚本会自动识别当前页面，页面右下角会出现蓝P悬浮小球，双击后就调用本地的exe进行图片的批量下载。
   

# Python Version

使用的是Python 3.11.

所需依赖在requirements.txt中。

# 仅供个人学习使用！