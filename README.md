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
