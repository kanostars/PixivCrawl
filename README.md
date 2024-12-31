# Pixiv下载器-直连版
## 项目介绍
Pixiv下载器-直连版是PixivCrawl的一个分支，旨在不使用vpn、加速器或者其他方式连接上Pixiv的情况下能够正常使用该下载器。

## 使用说明
该使用说明只列出与原版的差异。

选择浏览器路径（建议直接在浏览器exe文件中复制路径）后点击打开pixiv将通过选择的浏览器打开一个（不安全的）页面，用于访问pixiv有关网站。
打开浏览器时将关闭该浏览器的所有已打开的程序，如有未保存的页面，请谨慎使用该功能。

## 项目申明
Pixiv下载器-直连版不保证稳定连接，不保证版本为最新，功能与原下载器相比可能会有一定差异。
建议首选原下载器。
[原下载器](https://github.com/kanostars/PixivCrawl/tree/master)

Pixiv下载器-直连版不提供任何外网连接，只支持自身对Pixiv网站的连接。

Pixiv下载器-直连版只作为个人学习使用，无意违反相关法律政策及绕过国家审查。

## 项目原理
Pixiv下载器-直连版通过自定义包装SSL套接字绕过sni阻断达到连接Pixiv网站的目的。

## 
以下为原分支README内容。

# PixivCrawl
旨在通过画师ID或者插画ID下载对应的插画作品。
程序是先获取所以图片的大小信息，然后再将所有信息放入下载队列进行下载。如果其中有动图的话，会在最后拼接成gif。

[直连版入口](https://github.com/kanostars/PixivCrawl/tree/vpn)

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


（可选）js文件需要搭配浏览器插件（篡改猴测试版）使用

# Python Version
使用的是Python 3.11.
