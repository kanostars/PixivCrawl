# PixivCrawl
旨在通过画师ID或者插画ID下载对应的插画作品。
程序是先获取所以图片的大小信息，然后再将所有信息放入下载队列进行下载。如果其中有动图的话，会在最后拼接成gif。

# Python Version
使用的是Python 3.11.

# Notice
确保pixivCrawl.py文件和img文件夹在同一个路径下，且img含有一张名为“92260993.png”的图片。
- img
  - 92260993.png
- pixivCrawl.py
